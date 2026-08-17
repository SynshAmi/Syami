import sqlite3
from pathlib import Path


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

            FOREIGN KEY (last_seen_scan_id)
                REFERENCES scan_sessions(id)
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_scan_sessions_scope_id
        ON scan_sessions(scope_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_last_seen_scan
        ON documents(last_seen_scan_id)
    """)

    connection.commit()
    connection.close()