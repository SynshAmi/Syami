from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = PROJECT_ROOT / "data" / "syami.db"


def get_connection(db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def init_db(db_path=DB_PATH):
    connection = get_connection(db_path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS scan_scopes (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1
                CHECK (enabled IN (0, 1)),
            created_at REAL NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS user_exclusions (
            id INTEGER PRIMARY KEY,
            pattern TEXT NOT NULL,
            match_type TEXT NOT NULL
                CHECK (
                    match_type IN (
                        'directory',
                        'file',
                        'glob'
                    )
                ),
            enabled INTEGER NOT NULL DEFAULT 1
                CHECK (enabled IN (0, 1)),
            created_at REAL NOT NULL,

            UNIQUE(pattern, match_type)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS scan_sessions (
            id INTEGER PRIMARY KEY,
            scope_id INTEGER NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (
                    status IN (
                        'running',
                        'completed',
                        'failed'
                    )
                ),

            FOREIGN KEY (scope_id)
                REFERENCES scan_scopes(id)
                ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            extension TEXT,
            size INTEGER NOT NULL,
            created_at REAL NOT NULL,
            modified_at REAL NOT NULL,
            content_hash TEXT,

            processing_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (
                    processing_status IN (
                        'pending',
                        'processing',
                        'completed',
                        'failed',
                        'unsupported'
                    )
                ),

            processing_error TEXT,
            processing_started_at REAL,
            processed_at REAL,
            last_seen_scan_id INTEGER,

            filename_key TEXT,
            stem_key TEXT,
            path_key TEXT,

            FOREIGN KEY (last_seen_scan_id)
                REFERENCES scan_sessions(id)
        )
    """)

    # Backward-compatible schema evolution for existing databases
    cursor = connection.execute("PRAGMA table_info(documents)")
    existing_columns = {row["name"] for row in cursor.fetchall()}

    if "filename_key" not in existing_columns:
        connection.execute("ALTER TABLE documents ADD COLUMN filename_key TEXT")
    if "stem_key" not in existing_columns:
        connection.execute("ALTER TABLE documents ADD COLUMN stem_key TEXT")
    if "path_key" not in existing_columns:
        connection.execute("ALTER TABLE documents ADD COLUMN path_key TEXT")

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_scan_sessions_scope_id
        ON scan_sessions(scope_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_last_seen_scan
        ON documents(last_seen_scan_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_filename_key
        ON documents(filename_key)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_stem_key
        ON documents(stem_key)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_path_key
        ON documents(path_key)
    """)

    connection.commit()
    connection.close()


def get_documents_by_filename_key(
    connection: sqlite3.Connection,
    filename_key: str,
    limit: int = 25,
) -> list[sqlite3.Row]:
    if not filename_key:
        return []
    return connection.execute(
        """
        SELECT *
        FROM documents
        WHERE filename_key = ?
        LIMIT ?
        """,
        (filename_key, limit),
    ).fetchall()


def get_documents_by_stem_key(
    connection: sqlite3.Connection,
    stem_key: str,
    limit: int = 25,
) -> list[sqlite3.Row]:
    if not stem_key:
        return []
    return connection.execute(
        """
        SELECT *
        FROM documents
        WHERE stem_key = ?
        LIMIT ?
        """,
        (stem_key, limit),
    ).fetchall()


def get_documents_by_path_key(
    connection: sqlite3.Connection,
    path_key: str,
    limit: int = 25,
) -> list[sqlite3.Row]:
    if not path_key:
        return []
    return connection.execute(
        """
        SELECT *
        FROM documents
        WHERE path_key = ?
        LIMIT ?
        """,
        (path_key, limit),
    ).fetchall()


def get_documents_by_ids(
    connection: sqlite3.Connection,
    document_ids: list[int],
) -> dict[int, sqlite3.Row]:
    if not document_ids:
        return {}
    placeholders = ",".join("?" for _ in document_ids)
    rows = connection.execute(
        f"""
        SELECT *
        FROM documents
        WHERE id IN ({placeholders})
        """,
        tuple(document_ids),
    ).fetchall()
    return {row["id"]: row for row in rows}


def get_metadata_candidates(
    connection: sqlite3.Connection,
    extension: str | None = None,
    min_modified_at: float | None = None,
    max_modified_at: float | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    path_prefix: str | None = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    clauses = ["1=1"]
    params: list[Any] = []

    if extension is not None:
        clauses.append("extension = ?")
        params.append(extension.lower())
    if min_modified_at is not None:
        clauses.append("modified_at >= ?")
        params.append(min_modified_at)
    if max_modified_at is not None:
        clauses.append("modified_at <= ?")
        params.append(max_modified_at)
    if min_size is not None:
        clauses.append("size >= ?")
        params.append(min_size)
    if max_size is not None:
        clauses.append("size <= ?")
        params.append(max_size)
    if path_prefix is not None:
        clauses.append("path_key LIKE ?")
        params.append(f"{path_prefix.lower()}%")

    params.append(limit)
    query = f"""
        SELECT *
        FROM documents
        WHERE {' AND '.join(clauses)}
        ORDER BY modified_at DESC
        LIMIT ?
    """
    return connection.execute(query, tuple(params)).fetchall()