from enum import Enum


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"

from dataclasses import dataclass, field


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