import os
from pathlib import Path
import tempfile
import time
import unittest

from syami.application.indexing import index_directory
from syami.domain.document import ExtractionStatus
from syami.infrastructure.database.db import (
    get_connection,
    get_documents_by_filename_key,
    get_documents_by_stem_key,
)


class TestIndexingIdentityIntegration(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self._temp_dir.name) / "files"
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self._temp_dir.name) / "test_syami.db"

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_indexing_generates_identity_keys_and_handles_renames(self):
        # 1. Create a test file
        file_path = self.root_path / "IAI_Endsem.txt"
        file_path.write_text("Kalman filter contents for exam.", encoding="utf-8")

        # 2. Run initial indexing
        index_directory(str(self.root_path), db_path=self.db_path)

        conn = get_connection(self.db_path)
        try:
            # Verify identity keys stored on initial insert
            doc = conn.execute("SELECT * FROM documents WHERE filename = 'IAI_Endsem.txt'").fetchone()
            self.assertIsNotNone(doc)
            self.assertEqual(doc["filename_key"], "iai_endsem.txt")
            self.assertEqual(doc["stem_key"], "iai_endsem")
            self.assertEqual(doc["processing_status"], ExtractionStatus.PENDING.value)
            doc_id = doc["id"]

            # Mark document as completed (simulating document worker processing)
            conn.execute(
                "UPDATE documents SET processing_status = ? WHERE id = ?",
                (ExtractionStatus.COMPLETED.value, doc_id),
            )
            conn.commit()

            # Verify identity lookup
            by_stem = get_documents_by_stem_key(conn, "iai_endsem")
            self.assertEqual(len(by_stem), 1)
            self.assertEqual(by_stem[0]["id"], doc_id)
        finally:
            conn.close()

        # 3. Simulate a Rename/Move with unchanged content
        renamed_path = self.root_path / "IAI-Endsem-Final.txt"
        file_path.rename(renamed_path)

        index_directory(str(self.root_path), db_path=self.db_path)

        conn = get_connection(self.db_path)
        try:
            # Document ID should be preserved (rename detected via content hash)
            doc_renamed = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            self.assertIsNotNone(doc_renamed)
            self.assertEqual(doc_renamed["filename"], "IAI-Endsem-Final.txt")
            self.assertEqual(doc_renamed["filename_key"], "iai-endsem-final.txt")
            self.assertEqual(doc_renamed["stem_key"], "iai_endsem_final")

            # Processing status must REMAIN 'completed' (no unnecessary re-embedding)
            self.assertEqual(doc_renamed["processing_status"], ExtractionStatus.COMPLETED.value)

            # Old filename lookup should yield 0, new lookup should yield 1
            self.assertEqual(len(get_documents_by_filename_key(conn, "iai_endsem.txt")), 0)
            self.assertEqual(len(get_documents_by_filename_key(conn, "iai-endsem-final.txt")), 1)
        finally:
            conn.close()

        # 4. Simulate a content change (forces re-extraction)
        time.sleep(0.05) # ensure modified_at changes
        renamed_path.write_text("Updated Kalman filter content with new notes.", encoding="utf-8")

        index_directory(str(self.root_path), db_path=self.db_path)

        conn = get_connection(self.db_path)
        try:
            doc_updated = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            self.assertEqual(doc_updated["processing_status"], ExtractionStatus.PENDING.value)
        finally:
            conn.close()

        # 5. Simulate file deletion
        renamed_path.unlink()
        index_directory(str(self.root_path), db_path=self.db_path)

        conn = get_connection(self.db_path)
        try:
            doc_deleted = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            self.assertIsNone(doc_deleted)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
