import logging
import os
import time

from syami.application.exclusion.policy import ExclusionPolicy
from syami.domain.document import ExtractionStatus
from syami.infrastructure.database.db import get_connection, init_db
from syami.infrastructure.filesystem.hasher import calculate_file_hash
from syami.infrastructure.filesystem.scanner import scan_directory


logger = logging.getLogger(__name__)


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _get_or_create_scope(connection, root_path: str) -> int:
    existing = connection.execute(
        """
        SELECT id
        FROM scan_scopes
        WHERE path = ?
        """,
        (root_path,),
    ).fetchone()

    if existing is not None:
        return existing["id"]

    cursor = connection.execute(
        """
        INSERT INTO scan_scopes (
            path,
            enabled,
            created_at
        )
        VALUES (?, 1, ?)
        """,
        (root_path, time.time()),
    )

    return cursor.lastrowid


def _create_scan_session(connection, scope_id: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO scan_sessions (
            scope_id,
            started_at,
            status
        )
        VALUES (?, ?, 'running')
        """,
        (scope_id, time.time()),
    )

    connection.commit()

    return cursor.lastrowid


def _find_rename_candidate(
    connection,
    content_hash: str,
    scope_id: int,
    scan_id: int,
):
    rows = connection.execute(
        """
        SELECT
            d.id,
            d.path,
            d.content_hash
        FROM documents d
        JOIN scan_sessions s
            ON d.last_seen_scan_id = s.id
        WHERE s.scope_id = ?
          AND d.last_seen_scan_id != ?
          AND d.content_hash = ?
        """,
        (
            scope_id,
            scan_id,
            content_hash,
        ),
    ).fetchall()

    if len(rows) == 1:
        return rows[0]

    return None


def index_directory(root_path: str):
    init_db()

    root_path = _normalize_path(root_path)

    connection = get_connection()

    try:
        scope_id = _get_or_create_scope(
            connection,
            root_path,
        )

        scan_id = _create_scan_session(
            connection,
            scope_id,
        )

        policy = ExclusionPolicy()
        scan_errors = []

        def handle_scan_error(path, error):
            scan_errors.append((path, error))

            logger.warning(
                "Could not scan '%s': %s",
                path,
                error,
            )

        for file in scan_directory(
            root_path,
            should_exclude=policy.should_exclude,
            on_error=handle_scan_error,
        ):
            try:
                file.path = _normalize_path(file.path)

                existing = connection.execute(
                    """
                    SELECT
                        id,
                        size,
                        modified_at,
                        content_hash
                    FROM documents
                    WHERE path = ?
                    """,
                    (file.path,),
                ).fetchone()

                # ---------------------------------------------------------
                # Existing path
                # ---------------------------------------------------------
                if existing is not None:
                    metadata_changed = (
                        float(existing["size"])
                        != float(file.size)
                        or float(existing["modified_at"])
                        != float(file.modified_at)
                    )

                    if not metadata_changed:
                        connection.execute(
                            """
                            UPDATE documents
                            SET last_seen_scan_id = ?
                            WHERE id = ?
                            """,
                            (
                                scan_id,
                                existing["id"],
                            ),
                        )

                        logger.info(
                            "Skipped unchanged file: %s",
                            file.path,
                        )

                        continue

                    content_hash = calculate_file_hash(
                        file.path
                    )

                    if content_hash == existing["content_hash"]:
                        connection.execute(
                            """
                            UPDATE documents
                            SET
                                filename = ?,
                                extension = ?,
                                size = ?,
                                created_at = ?,
                                modified_at = ?,
                                last_seen_scan_id = ?
                            WHERE id = ?
                            """,
                            (
                                file.filename,
                                file.extension,
                                file.size,
                                file.created_at,
                                file.modified_at,
                                scan_id,
                                existing["id"],
                            ),
                        )

                        logger.info(
                            "Metadata changed but content unchanged: %s",
                            file.path,
                        )

                        continue

                    connection.execute(
                        """
                        UPDATE documents
                        SET
                            filename = ?,
                            extension = ?,
                            size = ?,
                            created_at = ?,
                            modified_at = ?,
                            content_hash = ?,
                            processing_status = ?,
                            processing_error = NULL,
                            processing_started_at = NULL,
                            processed_at = NULL,
                            last_seen_scan_id = ?
                        WHERE id = ?
                        """,
                        (
                            file.filename,
                            file.extension,
                            file.size,
                            file.created_at,
                            file.modified_at,
                            content_hash,
                            ExtractionStatus.PENDING.value,
                            scan_id,
                            existing["id"],
                        ),
                    )

                    logger.info(
                        "Detected content change: %s",
                        file.path,
                    )

                    continue

                # ---------------------------------------------------------
                # New path
                #
                # We must hash it because it may actually be a renamed
                # or moved document whose old path disappeared.
                # ---------------------------------------------------------
                content_hash = calculate_file_hash(
                    file.path
                )

                rename_candidate = _find_rename_candidate(
                    connection,
                    content_hash,
                    scope_id,
                    scan_id,
                )

                # ---------------------------------------------------------
                # Unique rename/move candidate
                # ---------------------------------------------------------
                if rename_candidate is not None:
                    connection.execute(
                        """
                        UPDATE documents
                        SET
                            path = ?,
                            filename = ?,
                            extension = ?,
                            size = ?,
                            created_at = ?,
                            modified_at = ?,
                            last_seen_scan_id = ?
                        WHERE id = ?
                        """,
                        (
                            file.path,
                            file.filename,
                            file.extension,
                            file.size,
                            file.created_at,
                            file.modified_at,
                            scan_id,
                            rename_candidate["id"],
                        ),
                    )

                    logger.info(
                        "Detected rename/move: %s → %s",
                        rename_candidate["path"],
                        file.path,
                    )

                    continue

                # ---------------------------------------------------------
                # Genuinely new document OR ambiguous duplicate content
                # ---------------------------------------------------------
                connection.execute(
                    """
                    INSERT INTO documents (
                        path,
                        filename,
                        extension,
                        size,
                        created_at,
                        modified_at,
                        content_hash,
                        processing_status,
                        last_seen_scan_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file.path,
                        file.filename,
                        file.extension,
                        file.size,
                        file.created_at,
                        file.modified_at,
                        content_hash,
                        ExtractionStatus.PENDING.value,
                        scan_id,
                    ),
                )

                logger.info(
                    "Indexed new file: %s",
                    file.path,
                )

            except (OSError, PermissionError) as error:
                logger.warning(
                    "Could not process file '%s': %s",
                    file.path,
                    error,
                )

                scan_errors.append(
                    (file.path, error)
                )

        # -------------------------------------------------------------
        # Never reconcile deletions if the scan wasn't clean.
        # -------------------------------------------------------------
        if scan_errors:
            connection.execute(
                """
                UPDATE scan_sessions
                SET
                    status = 'failed',
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    time.time(),
                    scan_id,
                ),
            )

            connection.commit()

            logger.warning(
                "Scan %s failed; deletion reconciliation skipped.",
                scan_id,
            )

            return

        # -------------------------------------------------------------
        # Successful scan:
        # documents from this scope not seen during this scan are gone.
        # -------------------------------------------------------------
        connection.execute(
            """
            DELETE FROM documents
            WHERE last_seen_scan_id != ?
              AND last_seen_scan_id IN (
                  SELECT id
                  FROM scan_sessions
                  WHERE scope_id = ?
              )
            """,
            (
                scan_id,
                scope_id,
            ),
        )

        connection.execute(
            """
            UPDATE scan_sessions
            SET
                status = 'completed',
                completed_at = ?
            WHERE id = ?
            """,
            (
                time.time(),
                scan_id,
            ),
        )

        connection.commit()

        logger.info(
            "Scan %s completed successfully.",
            scan_id,
        )

    except Exception:
        connection.rollback()

        logger.exception(
            "Indexing failed for scope: %s",
            root_path,
        )

        raise

    finally:
        connection.close()