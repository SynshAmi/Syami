import re
from typing import Any

from syami.domain.document import DocumentChunk, ProcessedDocument


class DocumentChunker:

    def __init__(
        self,
        target_chunk_size: int = 1000,
        max_chunk_size: int = 1500,
        overlap_size: int = 100,
    ):
        self._target_chunk_size = target_chunk_size
        self._max_chunk_size = max_chunk_size
        self._overlap_size = overlap_size

    def chunk(self, document: ProcessedDocument) -> list[DocumentChunk]:
        if not document.units:
            return []

        doc_type = document.document_type.lower()

        if doc_type == "pptx":
            raw_chunks = self._chunk_pptx(document)
        elif doc_type == "pdf":
            raw_chunks = self._chunk_pdf(document)
        elif doc_type == "docx":
            raw_chunks = self._chunk_docx(document)
        else:
            raw_chunks = self._chunk_text(document)

        chunks: list[DocumentChunk] = []

        for index, (text, metadata) in enumerate(raw_chunks, start=1):
            chunks.append(
                DocumentChunk(
                    document_id=document.document_id,
                    chunk_index=index,
                    text=text,
                    source_metadata=metadata,
                )
            )

        return chunks

    def _split_oversized_text(self, text: str) -> list[str]:
        text = text.strip()

        if not text:
            return []

        if len(text) <= self._max_chunk_size:
            return [text]

        paragraphs = text.split("\n\n")

        if len(paragraphs) > 1:
            chunks: list[str] = []
            current = ""

            for p in paragraphs:
                p = p.strip()

                if not p:
                    continue

                if len(p) > self._max_chunk_size:
                    if current:
                        chunks.append(current.strip())
                        current = ""

                    chunks.extend(self._split_oversized_text(p))
                    continue

                if not current:
                    current = p
                elif len(current) + len(p) + 2 <= self._max_chunk_size:
                    current = f"{current}\n\n{p}"
                else:
                    chunks.append(current.strip())
                    current = p

            if current:
                chunks.append(current.strip())

            return chunks

        sentences = re.split(r"(?<=[.?!])\s+", text)

        if len(sentences) > 1:
            chunks = []
            current = ""

            for s in sentences:
                s = s.strip()

                if not s:
                    continue

                if not current:
                    current = s
                elif len(current) + len(s) + 1 <= self._max_chunk_size:
                    current = f"{current} {s}"
                else:
                    chunks.append(current.strip())
                    overlap_prefix = (
                        current[-self._overlap_size:]
                        if len(current) > self._overlap_size
                        else current
                    )
                    current = f"{overlap_prefix} {s}"

            if current:
                chunks.append(current.strip())

            return chunks

        chunks = []
        start = 0
        step = max(1, self._max_chunk_size - self._overlap_size)

        while start < len(text):
            end = min(start + self._max_chunk_size, len(text))
            chunk_slice = text[start:end].strip()

            if chunk_slice:
                chunks.append(chunk_slice)

            if end >= len(text):
                break

            start += step

        return chunks

    def _chunk_pptx(
        self,
        document: ProcessedDocument,
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []

        for unit in document.units:
            text = unit.text.strip()

            if not text:
                continue

            metadata = {
                "unit_type": unit.unit_type,
                "slide_index": unit.unit_index,
            }

            if len(text) <= self._max_chunk_size:
                results.append((text, metadata))
            else:
                for sub_text in self._split_oversized_text(text):
                    results.append((sub_text, metadata))

        return results

    def _chunk_pdf(
        self,
        document: ProcessedDocument,
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []

        for unit in document.units:
            text = unit.text.strip()

            if not text:
                continue

            metadata = {
                "unit_type": unit.unit_type,
                "page_index": unit.unit_index,
            }

            if len(text) <= self._max_chunk_size:
                results.append((text, metadata))
            else:
                for sub_text in self._split_oversized_text(text):
                    results.append((sub_text, metadata))

        return results

    def _chunk_docx(
        self,
        document: ProcessedDocument,
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []
        current_paragraphs: list[str] = []
        current_length = 0
        start_index = None

        for unit in document.units:
            text = unit.text.strip()

            if not text:
                continue

            if start_index is None:
                start_index = unit.unit_index

            if len(text) > self._max_chunk_size:
                if current_paragraphs:
                    combined = "\n\n".join(current_paragraphs)
                    results.append((
                        combined,
                        {
                            "unit_type": "paragraph_group",
                            "paragraph_index": start_index,
                        },
                    ))
                    current_paragraphs = []
                    current_length = 0
                    start_index = None

                for sub_text in self._split_oversized_text(text):
                    results.append((
                        sub_text,
                        {
                            "unit_type": unit.unit_type,
                            "paragraph_index": unit.unit_index,
                        },
                    ))
                continue

            if current_length + len(text) + 2 <= self._target_chunk_size:
                current_paragraphs.append(text)
                current_length += len(text) + 2
            else:
                if current_paragraphs:
                    combined = "\n\n".join(current_paragraphs)
                    results.append((
                        combined,
                        {
                            "unit_type": "paragraph_group",
                            "paragraph_index": start_index,
                        },
                    ))

                current_paragraphs = [text]
                current_length = len(text)
                start_index = unit.unit_index

        if current_paragraphs:
            combined = "\n\n".join(current_paragraphs)
            results.append((
                combined,
                {
                    "unit_type": "paragraph_group",
                    "paragraph_index": start_index or 1,
                },
            ))

        return results

    def _chunk_text(
        self,
        document: ProcessedDocument,
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []
        current_lines: list[str] = []
        current_length = 0
        start_index = None

        for unit in document.units:
            text = unit.text.strip()

            if not text:
                continue

            if start_index is None:
                start_index = unit.unit_index

            if current_length + len(text) + 1 <= self._target_chunk_size:
                current_lines.append(text)
                current_length += len(text) + 1
            else:
                if current_lines:
                    combined = "\n".join(current_lines)
                    results.append((
                        combined,
                        {
                            "unit_type": "section",
                            "line_index": start_index,
                        },
                    ))

                current_lines = [text]
                current_length = len(text)
                start_index = unit.unit_index

        if current_lines:
            combined = "\n".join(current_lines)
            results.append((
                combined,
                {
                    "unit_type": "section",
                    "line_index": start_index or 1,
                },
            ))

        return results
