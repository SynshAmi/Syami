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
        auto_optimize_threshold: int = 50,
    ):
        self._db_path = Path(db_path)
        self._chunks_table_name = table_name or chunks_table_name
        self._documents_table_name = documents_table_name
        self._auto_optimize_threshold = auto_optimize_threshold
        self._db: Any | None = None

    def _maybe_auto_optimize(self, table: Any) -> None:
        if self._auto_optimize_threshold <= 0:
            return

        try:
            for index in table.list_indices():
                if str(getattr(index, "index_type", "")).upper() != "FTS":
                    continue

                unindexed = getattr(index, "num_unindexed_rows", 0)
                if unindexed >= self._auto_optimize_threshold:
                    table.optimize()
                    return
        except Exception:
            pass

    def _get_db(self) -> Any:
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self._db_path))

        return self._db

    def _get_table(self, table_name: str) -> Any | None:
        db = self._get_db()
        try:
            return db.open_table(table_name)
        except Exception:
            return None

    def _has_fts_index(self, table: Any, column_name: str) -> bool:
        try:
            indices = table.list_indices()
            for idx in indices:
                cols = getattr(idx, "columns", [])
                idx_type = str(getattr(idx, "index_type", "")).upper()
                if column_name in cols and idx_type == "FTS":
                    return True
        except Exception:
            pass
        return False

    def _ensure_fts_index(
        self,
        table_name: str,
        column_name: str,
    ) -> None:
        table = self._get_table(table_name)
        if table is None:
            return

        if self._has_fts_index(table, column_name):
            return

        try:
            table.create_index(column_name, config=FTS())
        except Exception:
            pass

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

        if table_name == self._chunks_table_name:
            self._ensure_fts_index(table_name, column_name="text")
        elif table_name == self._documents_table_name:
            self._ensure_fts_index(table_name, column_name="title")

        if table is not None:
            self._maybe_auto_optimize(table)

    def _delete_records_from_table(
        self,
        table_name: str,
        document_id: int,
    ) -> None:
        table = self._get_table(table_name)

        if table is not None:
            table.delete(f"document_id = {document_id}")

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

    def _search_table(
        self,
        table_name: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []

        table = self._get_table(table_name)
        if table is None:
            return []

        return (
            table.search(query.strip(), query_type="fts")
            .limit(limit)
            .to_list()
        )

    def search_titles(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self._search_table(
            self._documents_table_name,
            query,
            limit=limit,
        )

    def search_text(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self._search_table(
            self._chunks_table_name,
            query,
            limit=limit,
        )

    def optimize(self, table_name: str | None = None) -> None:
        """
        Optimizes dataset files and indices for LanceDB tables (compaction, pruning, and index update).
        """
        target_tables = (
            [table_name]
            if table_name is not None
            else [self._documents_table_name, self._chunks_table_name]
        )

        for name in target_tables:
            table = self._get_table(name)
            if table is not None:
                try:
                    table.optimize()
                except Exception:
                    pass
