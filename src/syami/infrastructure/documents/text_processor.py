from pathlib import Path

from syami.application.documents.processor import DocumentProcessor
from syami.domain.document import ContentUnit, ProcessedDocument


class TextProcessor(DocumentProcessor):

    def process(
        self,
        document_id: int,
        source_path: str,
    ) -> ProcessedDocument:

        path = Path(source_path)

        if not path.exists():
            raise FileNotFoundError(
                f"File does not exist: {path}"
            )

        if path.suffix.lower() not in {".txt", ".text", ".md"}:
            raise ValueError(
                f"Expected a text file: {path}"
            )

        units = []

        with open(path, "r", encoding="utf-8") as file:
            for index, line in enumerate(file, start=1):
                text = line.strip()

                if not text:
                    continue

                units.append(
                    ContentUnit(
                        text=text,
                        unit_type="line",
                        unit_index=index,
                    )
                )

        return ProcessedDocument(
            document_id=document_id,
            source_path=str(path),
            document_type="text",
            title=path.stem,
            units=units,
        )
