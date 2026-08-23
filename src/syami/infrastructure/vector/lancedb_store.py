from pathlib import Path
from typing import Any

import lancedb


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LANCE_DB_PATH = PROJECT_ROOT / "data" / "lancedb"


class LanceDBVectorStore:

    def __init__(
        self,
        db_path: Path | str = LANCE_DB_PATH,
        table_name: str = "chunks",
    ):
        self._db_path = Path(db_path)
        self._table_name = table_name
        self._db: Any | None = None

    def _get_db(self) -> Any:
        if self._db is None:
            self._db_path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self._db_path))

        return self._db

    def _get_table(self) -> Any | None:
        db = self._get_db()

        try:
            if hasattr(db, "table_names"):
                existing = db.table_names()
            elif hasattr(db, "list_tables"):
                existing = db.list_tables()
            else:
                existing = []

            if self._table_name in existing:
                return db.open_table(self._table_name)
        except Exception:
            try:
                return db.open_table(self._table_name)
            except Exception:
                return None

        return None

    def replace_document_chunks(
        self,
        document_id: int,
        records: list[dict[str, Any]],
        write_batch_size: int = 100,
    ) -> None:
        db = self._get_db()
        table = self._get_table()

        if table is not None:
            table.delete(f"document_id = {document_id}")

            if records:
                for i in range(0, len(records), write_batch_size):
                    batch = records[i:i + write_batch_size]
                    table.add(batch)
        else:
            if records:
                db.create_table(
                    self._table_name,
                    data=records[:write_batch_size],
                    mode="overwrite",
                )
                table = db.open_table(self._table_name)

                for i in range(write_batch_size, len(records), write_batch_size):
                    batch = records[i:i + write_batch_size]
                    table.add(batch)

    def delete_document_chunks(self, document_id: int) -> None:
        table = self._get_table()

        if table is not None:
            table.delete(f"document_id = {document_id}")
