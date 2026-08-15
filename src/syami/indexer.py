from .db import get_connection, init_db
from .scanner import scan_directory


def index_directory(root_path: str):
    init_db()

    connection = get_connection()

    try:
        for file in scan_directory(root_path):
            connection.execute(
                """
                INSERT INTO files (
                    path,
                    filename,
                    extension,
                    size,
                    created_at,
                    modified_at,
                    indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(path) DO UPDATE SET
                    filename = excluded.filename,
                    extension = excluded.extension,
                    size = excluded.size,
                    created_at = excluded.created_at,
                    modified_at = excluded.modified_at,
                    indexed_at = excluded.indexed_at
                """,
                (
                    file.path,
                    file.filename,
                    file.extension,
                    file.size,
                    file.created_at,
                    file.modified_at,
                    file.indexed_at,
                ),
            )

        connection.commit()

    finally:
        connection.close()