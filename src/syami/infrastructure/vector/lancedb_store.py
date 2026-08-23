from pathlib import Path
from typing import Any

import lancedb
from lancedb.index import FTS


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LANCE_DB_PATH = PROJECT_ROOT / "data" / "lancedb"


class LanceDBVectorStore:

    def __init__(
        self,
        db_path: Path | str = LANCE_DB_PATH,
        chunks_table_name: str = "chunks",
        documents_table_name: str = "documents",
        table_name: str | None = None,
    ):
        self._db_path = Path(db_path)
        self._chunks_table_name = table_name or chunks_table_name
        self._documents_table_name = documents_table_name
        self._db: Any | None = None

    def _get_db(self) -> Any:
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self._db_path))

        return self._db

    def _get_table(self, table_name: str) -> Any | None:
        db = self._get_db()

        try:
            if hasattr(db, "table_names"):
                existing = db.table_names()
            elif hasattr(db, "list_tables"):
                existing = db.list_tables()
            else:
                existing = []

            if table_name in existing:
                return db.open_table(table_name)
        except Exception:
            try:
                return db.open_table(table_name)
            except Exception:
                return None

        return None

    def _ensure_fts_index(
        self,
        table_name: str,
        column_name: str = "text",
    ) -> None:
        table = self._get_table(table_name)
        if table is None:
            return

        table.create_index(column_name, config=FTS(), replace=True)

    def _replace_records_in_table(
        self,
        table_name: str,
        document_id: int,
        records: list[dict[str, Any]],
        write_batch_size: int = 100,
    ) -> None:
        db = self._get_db()
        table = self._get_table(table_name)

        if table is not None:
            table.delete(f"document_id = {document_id}")

            if records:
                for i in range(0, len(records), write_batch_size):
                    batch = records[i:i + write_batch_size]
                    table.add(batch)
        else:
            if records:
                db.create_table(
                    table_name,
                    data=records[:write_batch_size],
                    mode="overwrite",
                )
                table = db.open_table(table_name)

                for i in range(write_batch_size, len(records), write_batch_size):
                    batch = records[i:i + write_batch_size]
                    table.add(batch)

        if table_name == self._chunks_table_name and (records or table is not None):
            self._ensure_fts_index(table_name, column_name="text")

    def _delete_records_from_table(
        self,
        table_name: str,
        document_id: int,
    ) -> None:
        table = self._get_table(table_name)

        if table is not None:
            table.delete(f"document_id = {document_id}")

            if table_name == self._chunks_table_name:
                self._ensure_fts_index(table_name, column_name="text")

    def replace_document(
        self,
        document_id: int,
        document_record: dict[str, Any] | None,
        chunk_records: list[dict[str, Any]],
        write_batch_size: int = 100,
    ) -> None:
        if document_record is not None:
            self._replace_records_in_table(
                self._documents_table_name,
                document_id,
                [document_record],
                write_batch_size=write_batch_size,
            )
        else:
            self._delete_records_from_table(
                self._documents_table_name,
                document_id,
            )

        self._replace_records_in_table(
            self._chunks_table_name,
            document_id,
            chunk_records,
            write_batch_size=write_batch_size,
        )

    def replace_document_chunks(
        self,
        document_id: int,
        records: list[dict[str, Any]],
        write_batch_size: int = 100,
    ) -> None:
        self._replace_records_in_table(
            self._chunks_table_name,
            document_id,
            records,
            write_batch_size=write_batch_size,
        )

    def delete_document(self, document_id: int) -> None:
        self._delete_records_from_table(
            self._documents_table_name,
            document_id,
        )
        self._delete_records_from_table(
            self._chunks_table_name,
            document_id,
        )

    def delete_document_chunks(self, document_id: int) -> None:
        self._delete_records_from_table(
            self._chunks_table_name,
            document_id,
        )

    def search_text(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []

        table = self._get_table(self._chunks_table_name)
        if table is None:
            return []

        return (
            table.search(query.strip(), query_type="fts")
            .limit(limit)
            .to_list()
        )



