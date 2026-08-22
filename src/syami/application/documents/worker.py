import time

from syami.application.documents.processing import DocumentProcessingService
from syami.domain.document import ExtractionStatus
from syami.infrastructure.database.db import get_connection


class DocumentProcessingWorker:

    def __init__(
        self,
        processing_service: DocumentProcessingService | None = None,
    ):
        self._processing_service = (
            processing_service or DocumentProcessingService()
        )

    def claim_pending_documents(
        self,
        batch_size: int = 10,
    ) -> list[int]:

        if batch_size <= 0:
            return []

        connection = get_connection()

        try:
            cursor = connection.execute(
                """
                WITH candidate_docs AS (
                    SELECT id
                    FROM documents
                    WHERE processing_status = ?
                    ORDER BY id ASC
                    LIMIT ?
                )
                UPDATE documents
                SET
                    processing_status = ?,
                    processing_started_at = ?,
                    processing_error = NULL
                WHERE id IN (SELECT id FROM candidate_docs)
                  AND processing_status = ?
                RETURNING id
                """,
                (
                    ExtractionStatus.PENDING.value,
                    batch_size,
                    ExtractionStatus.PROCESSING.value,
                    time.time(),
                    ExtractionStatus.PENDING.value,
                ),
            )

            rows = cursor.fetchall()
            connection.commit()

            return [row["id"] for row in rows]

        finally:
            connection.close()

    def process_claimed_documents(
        self,
        document_ids: list[int],
    ) -> dict[str, int]:

        stats = {
            "claimed": len(document_ids),
            "completed": 0,
            "unsupported": 0,
            "failed": 0,
        }

        for document_id in document_ids:
            try:
                result = self._processing_service.process_document(
                    document_id=document_id
                )

                if result is None:
                    stats["unsupported"] += 1
                else:
                    stats["completed"] += 1

            except Exception:
                stats["failed"] += 1

        return stats

    def run_once(
        self,
        batch_size: int = 10,
    ) -> dict[str, int]:

        claimed_ids = self.claim_pending_documents(batch_size=batch_size)

        if not claimed_ids:
            return {
                "claimed": 0,
                "completed": 0,
                "unsupported": 0,
                "failed": 0,
            }

        return self.process_claimed_documents(claimed_ids)

    def run(
        self,
        batch_size: int = 10,
    ) -> dict[str, int]:

        total_stats = {
            "claimed": 0,
            "completed": 0,
            "unsupported": 0,
            "failed": 0,
        }

        while True:
            batch_stats = self.run_once(batch_size=batch_size)

            if batch_stats["claimed"] == 0:
                break

            total_stats["claimed"] += batch_stats["claimed"]
            total_stats["completed"] += batch_stats["completed"]
            total_stats["unsupported"] += batch_stats["unsupported"]
            total_stats["failed"] += batch_stats["failed"]

        return total_stats
