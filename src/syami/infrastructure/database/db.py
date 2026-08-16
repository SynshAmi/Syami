import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = PROJECT_ROOT / "data" / "syami.db"


def get_connection(db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    return connection


def init_db(db_path=DB_PATH):
    connection = get_connection(db_path)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            extension TEXT,
            size INTEGER NOT NULL,
            created_at REAL NOT NULL,
            modified_at REAL NOT NULL,
            indexed_at REAL NOT NULL
        )
    """)

    connection.commit()
    connection.close()
