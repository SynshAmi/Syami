import sqlite3
import tempfile
import unittest
from pathlib import Path

from syami.infrastructure.database.db import (
    get_connection,
    get_documents_by_filename_key,
    get_documents_by_ids,
    get_documents_by_path_key,
    get_documents_by_stem_key,
    get_metadata_candidates,
    init_db,
)


class TestDBSchemaAndIdentity(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "test.db"

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_init_db_creates_columns_and_indexes(self):
        init_db(self.db_path)
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = {row["name"] for row in cursor.fetchall()}
            self.assertIn("filename_key", columns)
            self.assertIn("stem_key", columns)
            self.assertIn("path_key", columns)

            cursor = conn.execute("PRAGMA index_list(documents)")
            indexes = {row["name"] for row in cursor.fetchall()}
            self.assertIn("idx_documents_filename_key", indexes)
            self.assertIn("idx_documents_stem_key", indexes)
            self.assertIn("idx_documents_path_key", indexes)
        finally:
            conn.close()

    def test_schema_evolution_on_existing_database(self):
        # Create an old-style database without identity columns
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                extension TEXT,
                size INTEGER NOT NULL,
                created_at REAL NOT NULL,
                modified_at REAL NOT NULL,
                content_hash TEXT,
                processing_status TEXT NOT NULL DEFAULT 'pending',
                processing_error TEXT,
                processing_started_at REAL,
                processed_at REAL,
                last_seen_scan_id INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO documents (path, filename, extension, size, created_at, modified_at, content_hash)
            VALUES ('c:/docs/old.pdf', 'old.pdf', '.pdf', 100, 1.0, 2.0, 'hash123')
        """)
        conn.commit()
        conn.close()

        # Run init_db to evolve schema safely
        init_db(self.db_path)

        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = {row["name"] for row in cursor.fetchall()}
            self.assertIn("filename_key", columns)
            self.assertIn("stem_key", columns)
            self.assertIn("path_key", columns)

            # Ensure existing row is preserved
            row = conn.execute("SELECT * FROM documents WHERE id = 1").fetchone()
            self.assertEqual(row["filename"], "old.pdf")
            self.assertEqual(row["content_hash"], "hash123")
        finally:
            conn.close()

    def test_identity_lookups_and_hydration(self):
        init_db(self.db_path)
        conn = get_connection(self.db_path)
        try:
            conn.execute("""
                INSERT INTO documents (
                    path, filename, extension, size, created_at, modified_at,
                    content_hash, processing_status, filename_key, stem_key, path_key
                ) VALUES (
                    'c:/docs/iai_endsem.pdf', 'IAI_Endsem.pdf', '.pdf', 2048,
                    1700000000.0, 1700001000.0, 'hash_endsem', 'completed',
                    'iai_endsem.pdf', 'iai_endsem', 'c:/docs/iai_endsem.pdf'
                )
            """)
            conn.commit()

            # 1. Filename lookup
            fn_matches = get_documents_by_filename_key(conn, "iai_endsem.pdf")
            self.assertEqual(len(fn_matches), 1)
            self.assertEqual(fn_matches[0]["filename"], "IAI_Endsem.pdf")

            # 2. Stem lookup
            stem_matches = get_documents_by_stem_key(conn, "iai_endsem")
            self.assertEqual(len(stem_matches), 1)
            self.assertEqual(stem_matches[0]["stem_key"], "iai_endsem")

            # 3. Path lookup
            path_matches = get_documents_by_path_key(conn, "c:/docs/iai_endsem.pdf")
            self.assertEqual(len(path_matches), 1)
            self.assertEqual(path_matches[0]["id"], 1)

            # 4. Authoritative Hydration by ID
            hydrated = get_documents_by_ids(conn, [1, 999])
            self.assertIn(1, hydrated)
            self.assertNotIn(999, hydrated)
            self.assertEqual(hydrated[1]["content_hash"], "hash_endsem")

            # 5. Metadata candidates
            candidates = get_metadata_candidates(conn, extension=".pdf", min_size=1000)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["id"], 1)

            # 6. Negative metadata filter
            candidates_none = get_metadata_candidates(conn, extension=".docx")
            self.assertEqual(len(candidates_none), 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
