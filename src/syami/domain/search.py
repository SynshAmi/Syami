from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IdentityKind(str, Enum):
    PATH = "path"
    FILENAME = "filename"
    STEM = "stem"
    IDENTIFIER_SEQUENCE = "identifier_sequence"


class IdentityTier(str, Enum):
    NONE = "none"
    EXACT_PATH = "exact_path"
    EXACT_FILENAME = "exact_filename"
    EXACT_STEM = "exact_stem"
    IDENTIFIER = "identifier"


@dataclass
class IdentityProbe:
    raw_value: str
    normalized_value: str
    kind: IdentityKind
    source_span: tuple[int, int] | None = None
    specificity: float = 1.0
    origin: str = "query"


class MetadataConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MetadataEnforcement(str, Enum):
    MANDATORY = "mandatory"
    STRICT_PREFERRED = "strict_preferred"
    SOFT_ONLY = "soft_only"


class MetadataPrecision(str, Enum):
    EXACT = "exact"
    RANGE = "range"
    FUZZY = "fuzzy"
    SET = "set"


@dataclass
class MetadataPredicate:
    field: str
    operator: str
    canonical_value: Any
    source_span: tuple[int, int] | None = None
    confidence: MetadataConfidence = MetadataConfidence.MEDIUM
    enforcement: MetadataEnforcement = MetadataEnforcement.SOFT_ONLY
    precision: MetadataPrecision = MetadataPrecision.EXACT
    raw_text: str | None = None


class SearchMode(str, Enum):
    STANDARD = "standard"
    METADATA_DOMINANT = "metadata_dominant"
    IDENTITY_DOMINANT = "identity_dominant"
    RECENT = "recent"


class ImpliedSort(str, Enum):
    RELEVANCE = "relevance"
    RECENCY = "recency"
    SIZE = "size"


@dataclass
class SearchQueryPlan:
    original_text: str
    normalized_text: str
    topical_text: str | None = None
    semantic_text: str | None = None
    quoted_phrases: list[str] = field(default_factory=list)
    identity_probes: list[IdentityProbe] = field(default_factory=list)
    metadata_predicates: list[MetadataPredicate] = field(default_factory=list)
    mode: SearchMode = SearchMode.STANDARD
    implied_sort: ImpliedSort | None = None
    diagnostics: list[str] = field(default_factory=list)


class RetrievalChannel(str, Enum):
    IDENTITY = "identity"
    TITLE_BM25 = "title_bm25"
    CONTENT_BM25 = "content_bm25"
    TITLE_VECTOR = "title_vector"
    CONTENT_VECTOR = "content_vector"
    METADATA = "metadata"


@dataclass
class RetrievalCandidate:
    document_id: int
    channel: RetrievalChannel
    score: float
    rank: int
    chunk_index: int | None = None
    chunk_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EvidenceType(str, Enum):
    IDENTITY = "identity"
    TITLE_LEXICAL = "title_lexical"
    CONTENT_LEXICAL = "content_lexical"
    TITLE_SEMANTIC = "title_semantic"
    CONTENT_SEMANTIC = "content_semantic"
    METADATA = "metadata"
    DEGRADATION = "degradation"


@dataclass
class EvidenceItem:
    evidence_type: EvidenceType
    description: str
    snippet: str | None = None
    confidence: float | None = None
    source_channel: RetrievalChannel | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PassageEvidence:
    chunk_index: int
    text: str
    score: float
    channel: RetrievalChannel
    unit_type: str | None = None


@dataclass
class DocumentMetadata:
    id: int
    path: str
    filename: str
    extension: str | None = None
    size: int = 0
    created_at: float = 0.0
    modified_at: float = 0.0
    content_hash: str | None = None
    processing_status: str | None = None


@dataclass
class SearchResult:
    document_id: int
    document: DocumentMetadata | None = None
    final_score: float = 0.0
    identity_tier: IdentityTier = IdentityTier.NONE
    topical_score: float = 0.0
    metadata_adjustment: float = 0.0
    evidence: list[EvidenceItem] = field(default_factory=list)
    passages: list[PassageEvidence] = field(default_factory=list)
    channel_ranks: dict[str, int] = field(default_factory=dict)
    channel_scores: dict[str, float] = field(default_factory=dict)
