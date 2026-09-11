from datetime import datetime, timedelta
import os
from pathlib import Path
import re
from typing import Any
import unicodedata

from syami.domain.search import (
    IdentityKind,
    IdentityProbe,
    ImpliedSort,
    MetadataConfidence,
    MetadataEnforcement,
    MetadataPrecision,
    MetadataPredicate,
    SearchMode,
    SearchQueryPlan,
    generate_identity_keys,
    normalize_filename_key,
    normalize_path_key,
    normalize_stem_key,
)


class QueryPlanner:
    """
    Deterministic, bounded, and explainable query planner for Syami search.
    Converts a natural language / memory query into a structured SearchQueryPlan.
    """

    KNOWN_EXTENSIONS = {
        "pdf": ".pdf",
        "docx": ".docx",
        "doc": ".docx",
        "pptx": ".pptx",
        "ppt": ".pptx",
        "txt": ".txt",
        "text": ".txt",
        "md": ".md",
        "markdown": ".md",
        "py": ".py",
        "csv": ".csv",
        "xlsx": ".xlsx",
        "xls": ".xlsx",
        "json": ".json",
        "html": ".html",
        "htm": ".html",
        "zip": ".zip",
    }

    TYPE_NAME_MAP = {
        "pdf": (".pdf", "pdf"),
        "pdfs": (".pdf", "pdf"),
        "word": (".docx", "docx"),
        "word document": (".docx", "docx"),
        "word documents": (".docx", "docx"),
        "docx": (".docx", "docx"),
        "doc": (".docx", "docx"),
        "powerpoint": (".pptx", "pptx"),
        "presentation": (".pptx", "pptx"),
        "presentations": (".pptx", "pptx"),
        "slides": (".pptx", "pptx"),
        "slide": (".pptx", "pptx"),
        "pptx": (".pptx", "pptx"),
        "ppt": (".pptx", "pptx"),
        "text": (".txt", "text"),
        "text file": (".txt", "text"),
        "text files": (".txt", "text"),
        "txt": (".txt", "text"),
        "markdown": (".md", "markdown"),
        "md": (".md", "markdown"),
    }

    HEDGING_PATTERNS = [
        r"\bi\s+think(?:\s+it\s+was)?\b",
        r"\bmaybe\b",
        r"\bprobably\b",
        r"\bperhaps\b",
        r"\bmight\s+be\b",
        r"\bcould\s+be\b",
        r"\bsomething\s+like\b",
        r"\bsomething\s+about\b",
        r"\baround\b",
    ]

    COMMAND_PREFIXES = [
        r"^(?:find\s+(?:me\s+)?|search\s+(?:for\s+)?|look\s+(?:for\s+)?|show\s+(?:me\s+)?|locate\s+|get\s+(?:me\s+)?|where\s+is\s+)",
    ]

    UNRESOLVED_TEMPORAL_PATTERNS = [
        r"\blast\s+semester\b",
        r"\bthis\s+semester\b",
        r"\ba\s+while\s+ago\b",
        r"\bback\s+then\b",
        r"\bwhen\s+i\s+was\s+in\s+[a-zA-Z0-9_\s]+\b",
        r"\bfew\s+(?:days|weeks|months|years)\s+back\b",
        r"\bsome\s+time\s+ago\b",
        r"\bearlier\b",
    ]

    GENERIC_ENTITIES = {
        "file",
        "files",
        "document",
        "documents",
        "all",
        "any",
        "show",
        "find",
        "search",
        "get",
        "locate",
        "item",
        "items",
    }

    def __init__(self, reference_time: float | None = None):
        self._reference_time = reference_time

    def _get_now(self) -> datetime:
        if self._reference_time is not None:
            return datetime.fromtimestamp(self._reference_time)
        return datetime.now()

    def plan(self, raw_query: str) -> SearchQueryPlan:
        if not raw_query or not raw_query.strip():
            return SearchQueryPlan(
                original_text=raw_query or "",
                normalized_text="",
                topical_text=None,
                semantic_text=None,
                diagnostics=["Empty search query"],
            )

        original_text = raw_query
        normalized_text = unicodedata.normalize("NFKC", raw_query).strip()

        diagnostics: list[str] = []
        quoted_phrases: list[str] = []
        identity_probes: list[IdentityProbe] = []
        metadata_predicates: list[MetadataPredicate] = []

        # 1. Extract quoted phrases
        extracted_quotes = re.findall(r'["\']([^"\']+)["\']', normalized_text)
        for quote in extracted_quotes:
            q_clean = quote.strip()
            if q_clean:
                quoted_phrases.append(q_clean)

        # Working text for extraction and stripping
        working_text = normalized_text

        # 2. Check for overall hedging in query
        is_hedged_query = any(
            re.search(pat, working_text, re.IGNORECASE)
            for pat in self.HEDGING_PATTERNS
        )

        # 3. Detect unresolved temporal expressions
        for pat in self.UNRESOLVED_TEMPORAL_PATTERNS:
            match = re.search(pat, working_text, re.IGNORECASE)
            if match:
                diagnostics.append(
                    f"Unresolved temporal reference: '{match.group(0)}'"
                )
                working_text = (
                    working_text[: match.start()] + " " + working_text[match.end() :]
                )

        # 4. Extract Identity Probes
        working_text = self._extract_identity_probes(
            working_text, identity_probes
        )

        # 5. Extract Metadata Predicates
        working_text = self._extract_metadata_predicates(
            working_text, metadata_predicates, is_hedged_query, diagnostics
        )

        # 6. Clean up working text into topical/semantic text
        topical_text, semantic_text = self._extract_topical_text(working_text)

        # 7. Determine Mode and Implied Sort
        mode, implied_sort = self._determine_mode_and_sort(
            normalized_text,
            identity_probes,
            metadata_predicates,
            topical_text,
        )

        return SearchQueryPlan(
            original_text=original_text,
            normalized_text=normalized_text,
            topical_text=topical_text,
            semantic_text=semantic_text,
            quoted_phrases=quoted_phrases,
            identity_probes=identity_probes,
            metadata_predicates=metadata_predicates,
            mode=mode,
            implied_sort=implied_sort,
            diagnostics=diagnostics,
        )

    def _extract_identity_probes(
        self,
        text: str,
        probes: list[IdentityProbe],
    ) -> str:
        trimmed = text.strip()

        # A. Path match (e.g. C:/path/to/file.pdf or folder/file.txt)
        path_pattern = (
            r'(?:[a-zA-Z]:[\\/][^\s",\']+|[a-zA-Z0-9_.\-]+[\\/][a-zA-Z0-9_.\-\\/]+)'
        )
        for match in list(re.finditer(path_pattern, text)):
            raw_path = match.group(0)
            norm_path = normalize_path_key(raw_path)
            probes.append(
                IdentityProbe(
                    raw_value=raw_path,
                    normalized_value=norm_path,
                    kind=IdentityKind.PATH,
                    source_span=match.span(),
                    specificity=1.0,
                    origin="path_token",
                )
            )
            p_obj = Path(raw_path)
            if p_obj.suffix:
                fn_key = normalize_filename_key(p_obj.name)
                stem_key = normalize_stem_key(p_obj.stem)
                probes.append(
                    IdentityProbe(
                        raw_value=p_obj.name,
                        normalized_value=fn_key,
                        kind=IdentityKind.FILENAME,
                        source_span=match.span(),
                        specificity=0.95,
                        origin="path_filename",
                    )
                )
                probes.append(
                    IdentityProbe(
                        raw_value=p_obj.stem,
                        normalized_value=stem_key,
                        kind=IdentityKind.STEM,
                        source_span=match.span(),
                        specificity=0.9,
                        origin="path_stem",
                    )
                )
            text = text[: match.start()] + " " + text[match.end() :]

        # B. Whole-query Filename with spaces (e.g. "Transformers Notes.pdf" when not a path)
        trimmed_after_path = text.strip()
        if not ("/" in trimmed_after_path or "\\" in trimmed_after_path or (len(trimmed_after_path) > 1 and trimmed_after_path[1] == ":")):
            p_obj = Path(trimmed_after_path)
            if p_obj.suffix.lower().lstrip(".") in self.KNOWN_EXTENSIONS:
                fn_norm = normalize_filename_key(trimmed_after_path)
                stem_norm = normalize_stem_key(p_obj.stem)
                if not any(p.normalized_value == fn_norm for p in probes):
                    probes.append(
                        IdentityProbe(
                            raw_value=trimmed_after_path,
                            normalized_value=fn_norm,
                            kind=IdentityKind.FILENAME,
                            source_span=(0, len(trimmed_after_path)),
                            specificity=1.0,
                            origin="full_filename_query",
                        )
                    )
                if not any(p.normalized_value == stem_norm for p in probes):
                    probes.append(
                        IdentityProbe(
                            raw_value=p_obj.stem,
                            normalized_value=stem_norm,
                            kind=IdentityKind.STEM,
                            source_span=(0, len(p_obj.stem)),
                            specificity=0.95,
                            origin="full_stem_query",
                        )
                    )
                return ""

        # C. Embedded Filename match with known extension (e.g. IAI_Endsem.pdf, notes.md)
        ext_alternatives = "|".join(re.escape(ext) for ext in self.KNOWN_EXTENSIONS.keys())
        filename_pattern = rf"\b([a-zA-Z0-9_\-\.]+\.(?:{ext_alternatives}))\b"

        for match in list(re.finditer(filename_pattern, text, re.IGNORECASE)):
            raw_fn = match.group(1)
            norm_fn = normalize_filename_key(raw_fn)
            p_obj = Path(raw_fn)
            norm_stem = normalize_stem_key(p_obj.stem)

            if not any(p.normalized_value == norm_fn for p in probes):
                probes.append(
                    IdentityProbe(
                        raw_value=raw_fn,
                        normalized_value=norm_fn,
                        kind=IdentityKind.FILENAME,
                        source_span=match.span(1),
                        specificity=0.95,
                        origin="filename_token",
                    )
                )
            if not any(p.normalized_value == norm_stem for p in probes):
                probes.append(
                    IdentityProbe(
                        raw_value=p_obj.stem,
                        normalized_value=norm_stem,
                        kind=IdentityKind.STEM,
                        source_span=match.span(1),
                        specificity=0.9,
                        origin="filename_stem",
                    )
                )
            text = text[: match.start()] + " " + text[match.end() :]

        # D. Identifier sequences / Stem-like tokens (e.g. IAI_Endsem, CS601_A1, RFC2616)
        id_pattern = r"\b([a-zA-Z0-9]+[_\-][a-zA-Z0-9_\-]+)\b"
        for match in list(re.finditer(id_pattern, text)):
            raw_id = match.group(1)
            norm_stem = normalize_stem_key(raw_id)
            if not any(p.normalized_value == norm_stem for p in probes):
                probes.append(
                    IdentityProbe(
                        raw_value=raw_id,
                        normalized_value=norm_stem,
                        kind=IdentityKind.STEM,
                        source_span=match.span(1),
                        specificity=0.85,
                        origin="identifier_token",
                    )
                )

        return text

    def _extract_metadata_predicates(
        self,
        text: str,
        predicates: list[MetadataPredicate],
        is_hedged_query: bool,
        diagnostics: list[str],
    ) -> str:
        # A. File Type / Extension Predicates
        type_names_sorted = sorted(self.TYPE_NAME_MAP.keys(), key=len, reverse=True)
        type_pattern_str = "|".join(re.escape(t) for t in type_names_sorted)

        # 1. Mandatory format: "only PDFs", "strictly docx", "just pdfs"
        mandatory_pattern = (
            rf"\b(?:only|strictly|just)\s+({type_pattern_str})\b"
        )
        for match in list(re.finditer(mandatory_pattern, text, re.IGNORECASE)):
            type_term = match.group(1).lower()
            if type_term in self.TYPE_NAME_MAP:
                ext, doc_type = self.TYPE_NAME_MAP[type_term]
                predicates.append(
                    MetadataPredicate(
                        field="extension",
                        operator="eq",
                        canonical_value=ext,
                        source_span=match.span(),
                        confidence=MetadataConfidence.HIGH,
                        enforcement=MetadataEnforcement.MANDATORY,
                        precision=MetadataPrecision.EXACT,
                        raw_text=match.group(0),
                    )
                )
                text = text[: match.start()] + " " + text[match.end() :]

        # 2. Standard or Hedged file type
        standard_type_pattern = rf"\b({type_pattern_str})\b"
        for match in list(re.finditer(standard_type_pattern, text, re.IGNORECASE)):
            type_term = match.group(1).lower()
            if type_term in self.TYPE_NAME_MAP:
                ext, doc_type = self.TYPE_NAME_MAP[type_term]
                preceding = text[: match.start()]
                is_locally_hedged = is_hedged_query or any(
                    re.search(pat, preceding[-30:], re.IGNORECASE)
                    for pat in self.HEDGING_PATTERNS
                )

                conf = (
                    MetadataConfidence.LOW
                    if is_locally_hedged
                    else MetadataConfidence.MEDIUM
                )
                enf = (
                    MetadataEnforcement.SOFT_ONLY
                    if is_locally_hedged
                    else MetadataEnforcement.STRICT_PREFERRED
                )

                if not any(
                    p.field == "extension" and p.canonical_value == ext
                    for p in predicates
                ):
                    predicates.append(
                        MetadataPredicate(
                            field="extension",
                            operator="eq",
                            canonical_value=ext,
                            source_span=match.span(),
                            confidence=conf,
                            enforcement=enf,
                            precision=MetadataPrecision.EXACT,
                            raw_text=match.group(0),
                        )
                    )
                text = text[: match.start()] + " " + text[match.end() :]

        # B. Date Predicates
        now = self._get_now()
        start_of_today = datetime(now.year, now.month, now.day).timestamp()
        start_of_yesterday = (
            datetime(now.year, now.month, now.day) - timedelta(days=1)
        ).timestamp()
        start_of_this_week = (
            datetime(now.year, now.month, now.day)
            - timedelta(days=now.weekday())
        ).timestamp()
        start_of_last_week = (
            datetime(now.year, now.month, now.day)
            - timedelta(days=now.weekday() + 7)
        ).timestamp()
        start_of_this_month = datetime(now.year, now.month, 1).timestamp()
        start_of_last_year = datetime(now.year - 1, 1, 1).timestamp()
        start_of_this_year = datetime(now.year, 1, 1).timestamp()

        date_patterns = [
            (
                r"\b(?:modified\s+)?today\b",
                "gte",
                start_of_today,
            ),
            (
                r"\b(?:modified\s+)?yesterday\b",
                "between",
                (start_of_yesterday, start_of_today),
            ),
            (
                r"\b(?:modified\s+)?this\s+week\b",
                "gte",
                start_of_this_week,
            ),
            (
                r"\b(?:modified\s+)?last\s+week\b",
                "between",
                (start_of_last_week, start_of_this_week),
            ),
            (
                r"\b(?:modified\s+)?this\s+month\b",
                "gte",
                start_of_this_month,
            ),
            (
                r"\b(?:modified\s+)?last\s+year\b",
                "between",
                (start_of_last_year, start_of_this_year),
            ),
        ]

        for pat, op, val in date_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                preceding = text[: match.start()]
                is_locally_hedged = is_hedged_query or any(
                    re.search(h_pat, preceding[-30:], re.IGNORECASE)
                    for h_pat in self.HEDGING_PATTERNS
                )
                is_mandatory = bool(
                    re.search(r"\b(?:only|strictly)\b", preceding[-20:], re.IGNORECASE)
                )

                if is_mandatory:
                    conf = MetadataConfidence.HIGH
                    enf = MetadataEnforcement.MANDATORY
                elif is_locally_hedged:
                    conf = MetadataConfidence.LOW
                    enf = MetadataEnforcement.SOFT_ONLY
                else:
                    conf = MetadataConfidence.MEDIUM
                    enf = MetadataEnforcement.STRICT_PREFERRED

                predicates.append(
                    MetadataPredicate(
                        field="modified_at",
                        operator=op,
                        canonical_value=val,
                        source_span=match.span(),
                        confidence=conf,
                        enforcement=enf,
                        precision=MetadataPrecision.RANGE,
                        raw_text=match.group(0),
                    )
                )
                text = text[: match.start()] + " " + text[match.end() :]

        # C. Size Predicates
        size_num_pattern = r"\b(?:size\s*)?(>|>=|<|<=|larger\s+than|bigger\s+than|smaller\s+than|less\s+than|more\s+than)\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb|bytes?)\b"
        for match in list(re.finditer(size_num_pattern, text, re.IGNORECASE)):
            comparator, num_str, unit = match.groups()
            unit_lower = unit.lower()
            num = float(num_str)
            multiplier = 1
            if "kb" in unit_lower:
                multiplier = 1024
            elif "mb" in unit_lower:
                multiplier = 1024 * 1024
            elif "gb" in unit_lower:
                multiplier = 1024 * 1024 * 1024
            bytes_val = int(num * multiplier)

            op = "gte" if any(c in comparator.lower() for c in [">", "larger", "bigger", "more"]) else "lte"
            predicates.append(
                MetadataPredicate(
                    field="size",
                    operator=op,
                    canonical_value=bytes_val,
                    source_span=match.span(),
                    confidence=MetadataConfidence.HIGH,
                    enforcement=MetadataEnforcement.STRICT_PREFERRED,
                    precision=MetadataPrecision.EXACT,
                    raw_text=match.group(0),
                )
            )
            text = text[: match.start()] + " " + text[match.end() :]

        large_match = re.search(r"\b(?:large|big)\s+(?:files?|documents?)\b", text, re.IGNORECASE)
        if large_match:
            predicates.append(
                MetadataPredicate(
                    field="size",
                    operator="gte",
                    canonical_value=5 * 1024 * 1024,
                    source_span=large_match.span(),
                    confidence=MetadataConfidence.LOW,
                    enforcement=MetadataEnforcement.SOFT_ONLY,
                    precision=MetadataPrecision.RANGE,
                    raw_text=large_match.group(0),
                )
            )
            text = text[: large_match.start()] + " " + text[large_match.end() :]

        small_match = re.search(r"\b(?:small|tiny)\s+(?:files?|documents?)\b", text, re.IGNORECASE)
        if small_match:
            predicates.append(
                MetadataPredicate(
                    field="size",
                    operator="lte",
                    canonical_value=100 * 1024,
                    source_span=small_match.span(),
                    confidence=MetadataConfidence.LOW,
                    enforcement=MetadataEnforcement.SOFT_ONLY,
                    precision=MetadataPrecision.RANGE,
                    raw_text=small_match.group(0),
                )
            )
            text = text[: small_match.start()] + " " + text[small_match.end() :]

        # D. Location / Folder cues
        folder_pattern = r"\b(?:in|under|inside)\s+(?:the\s+|my\s+)?(?:folder|directory)\s+[\"']?([a-zA-Z0-9_\-]+)[\"']?"
        for match in list(re.finditer(folder_pattern, text, re.IGNORECASE)):
            folder_name = match.group(1).strip()
            predicates.append(
                MetadataPredicate(
                    field="path_prefix",
                    operator="contains",
                    canonical_value=folder_name.lower(),
                    source_span=match.span(),
                    confidence=MetadataConfidence.MEDIUM,
                    enforcement=MetadataEnforcement.STRICT_PREFERRED,
                    precision=MetadataPrecision.FUZZY,
                    raw_text=match.group(0),
                )
            )
            text = text[: match.start()] + " " + text[match.end() :]

        folder_pattern2 = r"\b(?:in|under)\s+(?:my\s+)?([a-zA-Z0-9_\-]+)\s+(?:folder|directory)\b"
        for match in list(re.finditer(folder_pattern2, text, re.IGNORECASE)):
            folder_name = match.group(1).strip()
            if not any(p.field == "path_prefix" and p.canonical_value == folder_name.lower() for p in predicates):
                predicates.append(
                    MetadataPredicate(
                        field="path_prefix",
                        operator="contains",
                        canonical_value=folder_name.lower(),
                        source_span=match.span(),
                        confidence=MetadataConfidence.MEDIUM,
                        enforcement=MetadataEnforcement.STRICT_PREFERRED,
                        precision=MetadataPrecision.FUZZY,
                        raw_text=match.group(0),
                    )
                )
            text = text[: match.start()] + " " + text[match.end() :]

        return text

    def _extract_topical_text(self, text: str) -> tuple[str | None, str | None]:
        cleaned = text
        for pat in self.COMMAND_PREFIXES:
            cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

        scaffolding_words = [
            r"\babout\b",
            r"\bdiscussing\b",
            r"\brelated\s+to\b",
            r"\bmentioning\b",
            r"\bcontaining\b",
            r"\bwith\b",
            r"\bfor\b",
            r"\bthe\b",
            r"\ba\b",
            r"\ban\b",
            r"\bmy\b",
            r"\bour\b",
            r"\bfile\b",
            r"\bfiles\b",
            r"\bdocument\b",
            r"\bdocuments\b",
            r"\bnotes\b",
        ]

        semantic_candidate = re.sub(r'["\']', '', cleaned).strip()
        semantic_candidate = re.sub(r'\s+', ' ', semantic_candidate).strip(" ,.-_")

        topical_candidate = cleaned
        for pat in self.HEDGING_PATTERNS:
            topical_candidate = re.sub(pat, " ", topical_candidate, flags=re.IGNORECASE)
        for pat in scaffolding_words:
            topical_candidate = re.sub(pat, " ", topical_candidate, flags=re.IGNORECASE)

        topical_candidate = re.sub(r'["\']', '', topical_candidate).strip()
        topical_candidate = re.sub(r'\s+', ' ', topical_candidate).strip(" ,.-_")

        # Check if the words in candidate are exclusively generic/scaffolding
        semantic_words = set(semantic_candidate.lower().split()) if semantic_candidate else set()
        if not semantic_candidate or len(semantic_candidate) < 2 or semantic_words.issubset(self.GENERIC_ENTITIES):
            return None, None

        topical_words = set(topical_candidate.lower().split()) if topical_candidate else set()
        if not topical_candidate or len(topical_candidate) < 2 or topical_words.issubset(self.GENERIC_ENTITIES):
            topical_text = semantic_candidate
        else:
            topical_text = topical_candidate

        return topical_text, semantic_candidate

    def _determine_mode_and_sort(
        self,
        normalized_text: str,
        identity_probes: list[IdentityProbe],
        metadata_predicates: list[MetadataPredicate],
        topical_text: str | None,
    ) -> tuple[SearchMode, ImpliedSort | None]:
        # 1. Explicit Recent/Browsing Mode
        if re.search(r"\b(?:recent|recently\s+modified|latest|newest)\s+(?:files?|documents?)?\b", normalized_text, re.IGNORECASE):
            return SearchMode.RECENT, ImpliedSort.RECENCY

        # 2. Identity-Dominant: if query is solely a path or filename
        if identity_probes and (not topical_text or any(topical_text.lower() == p.raw_value.lower() for p in identity_probes)):
            return SearchMode.IDENTITY_DOMINANT, ImpliedSort.RELEVANCE

        # 3. Metadata-Dominant: metadata predicates exist with no topical text
        if metadata_predicates and not topical_text:
            if any(p.field == "modified_at" for p in metadata_predicates):
                return SearchMode.METADATA_DOMINANT, ImpliedSort.RECENCY
            if any(p.field == "size" for p in metadata_predicates):
                return SearchMode.METADATA_DOMINANT, ImpliedSort.SIZE
            return SearchMode.METADATA_DOMINANT, ImpliedSort.RELEVANCE

        # 4. Standard
        return SearchMode.STANDARD, ImpliedSort.RELEVANCE


def plan_query(raw_query: str, reference_time: float | None = None) -> SearchQueryPlan:
    """Convenience functional entry point for query planning."""
    planner = QueryPlanner(reference_time=reference_time)
    return planner.plan(raw_query)
