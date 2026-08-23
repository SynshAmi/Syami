from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


@dataclass
class ContentUnit:
    text: str
    unit_type: str
    unit_index: int


@dataclass
class ProcessedDocument:
    document_id: int
    source_path: str
    document_type: str
    title: str | None
    units: list[ContentUnit] = field(default_factory=list)


@dataclass
class DocumentChunk:
    document_id: int
    chunk_index: int
    text: str
    source_metadata: dict[str, Any] = field(default_factory=dict)