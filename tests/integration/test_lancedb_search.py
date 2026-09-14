import math
from pathlib import Path
import tempfile
import unittest

from syami.infrastructure.embedding.embedder import SentenceTransformerEmbedder
from syami.infrastructure.vector.lancedb_store import LanceDBVectorStore


class TestLanceDBRetrievalIntegration(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "lancedb"
        self.vector_store = LanceDBVectorStore(db_path=self.db_path)
        self.embedder = SentenceTransformerEmbedder()

        # Seed test documents and chunks into LanceDB
        # Doc 1: Java top 50 interview questions PDF
        doc1_title = "Java Top 50 Interview Questions"
        doc1_vec = self.embedder.embed_text(doc1_title)
        self.doc1_record = {
            "document_id": 1,
            "title": doc1_title,
            "title_vector": doc1_vec,
            "source_path": "C:/docs/java_interview.pdf",
            "document_type": "pdf",
        }
        self.doc1_chunks = [
            {
                "document_id": 1,
                "chunk_index": 0,
                "text": "What is IOC in Spring? Inversion of Control is a core principle in Spring framework.",
                "vector": self.embedder.embed_text("What is IOC in Spring? Inversion of Control is a core principle in Spring framework."),
                "title": doc1_title,
                "source_path": "C:/docs/java_interview.pdf",
                "document_type": "pdf",
                "unit_type": "paragraph",
            },
            {
                "document_id": 1,
                "chunk_index": 1,
                "text": "What is dependency injection? Dependency injection is a pattern implementing IOC.",
                "vector": self.embedder.embed_text("What is dependency injection? Dependency injection is a pattern implementing IOC."),
                "title": doc1_title,
                "source_path": "C:/docs/java_interview.pdf",
                "document_type": "pdf",
                "unit_type": "paragraph",
            },
            {
                "document_id": 1,
                "chunk_index": 2,
                "text": "What is the difference between JDK, JRE and JVM in Java virtual machine ecosystem?",
                "vector": self.embedder.embed_text("What is the difference between JDK, JRE and JVM in Java virtual machine ecosystem?"),
                "title": doc1_title,
                "source_path": "C:/docs/java_interview.pdf",
                "document_type": "pdf",
                "unit_type": "paragraph",
            },
        ]
        self.vector_store.replace_document(
            document_id=1,
            document_record=self.doc1_record,
            chunk_records=self.doc1_chunks,
        )

        # Doc 2: Python Data Science Handbook DOCX
        doc2_title = "Python Data Science Handbook"
        doc2_vec = self.embedder.embed_text(doc2_title)
        self.doc2_record = {
            "document_id": 2,
            "title": doc2_title,
            "title_vector": doc2_vec,
            "source_path": "C:/docs/python_ds.docx",
            "document_type": "docx",
        }
        self.doc2_chunks = [
            {
                "document_id": 2,
                "chunk_index": 0,
                "text": "Introduction to NumPy arrays and Pandas dataframes for data science.",
                "vector": self.embedder.embed_text("Introduction to NumPy arrays and Pandas dataframes for data science."),
                "title": doc2_title,
                "source_path": "C:/docs/python_ds.docx",
                "document_type": "docx",
                "unit_type": "paragraph",
            },
            {
                "document_id": 2,
                "chunk_index": 1,
                "text": "Machine learning algorithms with Scikit-Learn including gradient descent and regression.",
                "vector": self.embedder.embed_text("Machine learning algorithms with Scikit-Learn including gradient descent and regression."),
                "title": doc2_title,
                "source_path": "C:/docs/python_ds.docx",
                "document_type": "docx",
                "unit_type": "paragraph",
            },
        ]
        self.vector_store.replace_document(
            document_id=2,
            document_record=self.doc2_record,
            chunk_records=self.doc2_chunks,
        )

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_query_embedding_boundary(self):
        """Verify query embedding produces 384-dimensional normalized vector."""
        vec = self.embedder.embed_query("Java Spring dependency injection")
        self.assertEqual(len(vec), 384)

        # Check vector is non-zero and approximately unit-normalized
        norm = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(norm, 1.0, places=4)

        empty_vec = self.embedder.embed_query("")
        self.assertEqual(empty_vec, [])

    def test_title_lexical_retrieval(self):
        """Verify title lexical/FTS search against documents table."""
        results = self.vector_store.search_titles_lexical("Java Interview", limit=5)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["document_id"], 1)
        self.assertIn("Java", results[0]["title"])

        # Empty query handling
        empty_res = self.vector_store.search_titles_lexical("", limit=5)
        self.assertEqual(empty_res, [])

    def test_content_lexical_retrieval(self):
        """Verify content lexical/FTS search against chunks table."""
        results = self.vector_store.search_content_lexical("dependency injection", limit=5)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["document_id"], 1)
        self.assertEqual(results[0]["chunk_index"], 1)
        self.assertIn("dependency injection", results[0]["text"].lower())

    def test_title_vector_retrieval_with_explicit_column(self):
        """Verify title vector search explicitly queries title_vector column."""
        query_vec = self.embedder.embed_query("Java programming questions")
        results = self.vector_store.search_titles_vector(query_vec, limit=5)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["document_id"], 1)
        self.assertIn("Java", results[0]["title"])

    def test_content_vector_retrieval(self):
        """Verify content vector search queries chunks table vector column."""
        query_vec = self.embedder.embed_query("NumPy and Pandas tabular data manipulation")
        results = self.vector_store.search_content_vector(query_vec, limit=5)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["document_id"], 2)
        self.assertEqual(results[0]["chunk_index"], 0)

    def test_filtered_lexical_retrieval(self):
        """Verify metadata filtering in lexical search."""
        # Querying for something in both or checking filter exclusion
        results_pdf = self.vector_store.search_titles_lexical(
            "Handbook",
            limit=5,
            filter_expr="document_type = 'pdf'",
        )
        self.assertEqual(len(results_pdf), 0)

        results_docx = self.vector_store.search_titles_lexical(
            "Handbook",
            limit=5,
            filter_expr="document_type = 'docx'",
        )
        self.assertEqual(len(results_docx), 1)
        self.assertEqual(results_docx[0]["document_id"], 2)

    def test_filtered_vector_retrieval(self):
        """Verify metadata filtering in vector search."""
        query_vec = self.embedder.embed_query("Software guide")
        # Filter to only docx
        results_docx = self.vector_store.search_titles_vector(
            query_vec,
            limit=5,
            filter_expr="document_type = 'docx'",
        )
        self.assertTrue(len(results_docx) >= 1)
        for r in results_docx:
            self.assertEqual(r["document_type"], "docx")

    def test_metadata_only_update_without_reembedding(self):
        """Verify metadata updates modify documents and chunks without changing embeddings."""
        self.vector_store.update_document_metadata(
            document_id=1,
            metadata_updates={
                "source_path": "C:/new_path/java_interview_renamed.pdf",
                "title": "Renamed Java Questions",
            },
        )

        doc_res = self.vector_store.search_titles_lexical("Renamed Java", limit=5)
        self.assertTrue(len(doc_res) >= 1)
        self.assertEqual(doc_res[0]["document_id"], 1)
        self.assertEqual(doc_res[0]["title"], "Renamed Java Questions")
        self.assertEqual(doc_res[0]["source_path"], "C:/new_path/java_interview_renamed.pdf")

        chunk_res = self.vector_store.search_content_lexical("IOC", limit=5)
        self.assertTrue(len(chunk_res) >= 1)
        self.assertEqual(chunk_res[0]["source_path"], "C:/new_path/java_interview_renamed.pdf")

    def test_document_deletion_synchronization(self):
        """Verify delete_document removes entries from both documents and chunks tables."""
        self.vector_store.delete_document(document_id=1)

        doc_res = self.vector_store.search_titles_lexical("Java", limit=5)
        self.assertEqual(len(doc_res), 0)

        chunk_res = self.vector_store.search_content_lexical("IOC", limit=5)
        self.assertEqual(len(chunk_res), 0)

        # Document 2 should still be intact
        doc2_res = self.vector_store.search_titles_lexical("Python", limit=5)
        self.assertEqual(len(doc2_res), 1)
        self.assertEqual(doc2_res[0]["document_id"], 2)


if __name__ == "__main__":
    unittest.main()
