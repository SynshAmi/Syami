from pathlib import Path
import time

from syami.application.documents.chunker import DocumentChunker
from syami.domain.document import (
    ExtractionStatus,
    ProcessedDocument,
)
from syami.infrastructure.database.db import get_connection
from syami.infrastructure.documents.docx_processor import DOCXProcessor
from syami.infrastructure.documents.pdf_processor import PDFProcessor
from syami.infrastructure.documents.pptx_processor import PPTXProcessor
from syami.infrastructure.documents.text_processor import TextProcessor
from syami.infrastructure.embedding.embedder import SentenceTransformerEmbedder
from syami.infrastructure.vector.lancedb_store import LanceDBVectorStore


class DocumentProcessingService:

    def __init__(
        self,
        chunker: DocumentChunker | None = None,
        embedder: SentenceTransformerEmbedder | None = None,
        vector_store: LanceDBVectorStore | None = None,
    ):
        text_processor = TextProcessor()

        self._processors = {
            ".pdf": PDFProcessor(),
            ".docx": DOCXProcessor(),
            ".pptx": PPTXProcessor(),
            ".txt": text_processor,
            ".text": text_processor,
            ".md": text_processor,
        }

        self._chunker = chunker or DocumentChunker()
        self._embedder = embedder or SentenceTransformerEmbedder()
        self._vector_store = vector_store or LanceDBVectorStore()

    def process_document(
        self,
        document_id: int,
    ) -> ProcessedDocument | None:

        connection = get_connection()

        try:
            document = connection.execute(
                """
                SELECT
                    id,
                    path,
                    extension,
                    processing_status
                FROM documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()

            if document is None:
                raise ValueError(
                    f"Document not found: {document_id}"
                )

            extension = Path(document["path"]).suffix.lower()

            processor = self._processors.get(extension)

            if processor is None:
                connection.execute(
                    """
                    UPDATE documents
                    SET
                        processing_status = ?,
                        processed_at = ?
                    WHERE id = ?
                    """,
                    (
                        ExtractionStatus.UNSUPPORTED.value,
                        time.time(),
                        document_id,
                    ),
                )

                connection.commit()

                return None

            processed_document = processor.process(
                document_id=document["id"],
                source_path=document["path"],
            )

            chunks = self._chunker.chunk(processed_document)

            if chunks:
                texts = [c.text for c in chunks]
                embeddings = self._embedder.embed_chunks(texts)

                records = []
                for chunk, vector in zip(chunks, embeddings):
                    records.append({
                        "document_id": document["id"],
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                        "vector": vector,
                        "title": processed_document.title or "",
                        "source_path": processed_document.source_path,
                        "document_type": processed_document.document_type,
                        "unit_type": str(
                            chunk.source_metadata.get("unit_type", "")
                        ),
                    })

                self._vector_store.replace_document_chunks(
                    document_id=document["id"],
                    records=records,
                )
            else:
                self._vector_store.delete_document_chunks(
                    document_id=document["id"]
                )

            connection.execute(
                """
                UPDATE documents
                SET
                    processing_status = ?,
                    processed_at = ?
                WHERE id = ?
                """,
                (
                    ExtractionStatus.COMPLETED.value,
                    time.time(),
                    document_id,
                ),
            )

            connection.commit()

            return processed_document

        except Exception as error:
            connection.execute(
                """
                UPDATE documents
                SET
                    processing_status = ?,
                    processing_error = ?,
                    processed_at = ?
                WHERE id = ?
                """,
                (
                    ExtractionStatus.FAILED.value,
                    str(error),
                    time.time(),
                    document_id,
                ),
            )

            connection.commit()

            raise

        finally:
            connection.close()