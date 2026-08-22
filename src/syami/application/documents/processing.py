from pathlib import Path
import time

from syami.domain.document import (
    ExtractionStatus,
    ProcessedDocument,
)
from syami.infrastructure.database.db import get_connection
from syami.infrastructure.documents.pdf_processor import PDFProcessor
from syami.infrastructure.documents.docx_processor import DOCXProcessor
from syami.infrastructure.documents.pptx_processor import PPTXProcessor
from syami.infrastructure.documents.text_processor import TextProcessor


class DocumentProcessingService:

    def __init__(self):
        text_processor = TextProcessor()

        self._processors = {
            ".pdf": PDFProcessor(),
            ".docx": DOCXProcessor(),
            ".pptx": PPTXProcessor(),
            ".txt": text_processor,
            ".text": text_processor,
            ".md": text_processor,
        }

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

            connection.execute(
                """
                UPDATE documents
                SET
                    processing_status = ?,
                    processing_started_at = ?,
                    processing_error = NULL
                WHERE id = ?
                """,
                (
                    ExtractionStatus.PROCESSING.value,
                    time.time(),
                    document_id,
                ),
            )

            connection.commit()

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