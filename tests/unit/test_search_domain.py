import unittest

from syami.domain.search import (
    DocumentMetadata,
    EvidenceItem,
    EvidenceType,
    IdentityKind,
    IdentityProbe,
    IdentityTier,
    ImpliedSort,
    MetadataConfidence,
    MetadataEnforcement,
    MetadataPrecision,
    MetadataPredicate,
    PassageEvidence,
    RetrievalCandidate,
    RetrievalChannel,
    SearchMode,
    SearchQueryPlan,
    SearchResult,
)


class TestSearchDomainContracts(unittest.TestCase):

    def test_identity_enums_and_probe(self):
        self.assertEqual(IdentityKind.PATH.value, "path")
        self.assertEqual(IdentityKind.FILENAME.value, "filename")
        self.assertEqual(IdentityKind.STEM.value, "stem")
        self.assertEqual(IdentityKind.IDENTIFIER_SEQUENCE.value, "identifier_sequence")

        probe = IdentityProbe(
            raw_value="report.pdf",
            normalized_value="report.pdf",
            kind=IdentityKind.FILENAME,
            source_span=(0, 10),
            specificity=1.0,
            origin="query",
        )

        self.assertEqual(probe.raw_value, "report.pdf")
        self.assertEqual(probe.kind, IdentityKind.FILENAME)
        self.assertEqual(probe.source_span, (0, 10))
        self.assertEqual(probe.specificity, 1.0)

    def test_metadata_enums_and_predicate(self):
        self.assertEqual(MetadataConfidence.HIGH.value, "high")
        self.assertEqual(MetadataConfidence.MEDIUM.value, "medium")
        self.assertEqual(MetadataConfidence.LOW.value, "low")

        self.assertEqual(MetadataEnforcement.MANDATORY.value, "mandatory")
        self.assertEqual(MetadataEnforcement.STRICT_PREFERRED.value, "strict_preferred")
        self.assertEqual(MetadataEnforcement.SOFT_ONLY.value, "soft_only")

        self.assertEqual(MetadataPrecision.EXACT.value, "exact")
        self.assertEqual(MetadataPrecision.RANGE.value, "range")
        self.assertEqual(MetadataPrecision.FUZZY.value, "fuzzy")
        self.assertEqual(MetadataPrecision.SET.value, "set")

        predicate = MetadataPredicate(
            field="extension",
            operator="eq",
            canonical_value=".pdf",
            source_span=(0, 4),
            confidence=MetadataConfidence.HIGH,
            enforcement=MetadataEnforcement.MANDATORY,
            precision=MetadataPrecision.EXACT,
            raw_text="only PDFs",
        )

        self.assertEqual(predicate.field, "extension")
        self.assertEqual(predicate.operator, "eq")
        self.assertEqual(predicate.canonical_value, ".pdf")
        self.assertEqual(predicate.confidence, MetadataConfidence.HIGH)
        self.assertEqual(predicate.enforcement, MetadataEnforcement.MANDATORY)

    def test_search_query_plan_defaults_and_fields(self):
        plan = SearchQueryPlan(
            original_text="kalman filter pdf",
            normalized_text="kalman filter pdf",
            topical_text="kalman filter",
            semantic_text="kalman filter",
            quoted_phrases=["kalman filter"],
            identity_probes=[
                IdentityProbe(
                    raw_value="kalman",
                    normalized_value="kalman",
                    kind=IdentityKind.STEM,
                )
            ],
            metadata_predicates=[
                MetadataPredicate(
                    field="extension",
                    operator="eq",
                    canonical_value=".pdf",
                    confidence=MetadataConfidence.MEDIUM,
                    enforcement=MetadataEnforcement.STRICT_PREFERRED,
                )
            ],
            mode=SearchMode.STANDARD,
            implied_sort=ImpliedSort.RELEVANCE,
            diagnostics=["test diagnostic"],
        )

        self.assertEqual(plan.original_text, "kalman filter pdf")
        self.assertEqual(plan.topical_text, "kalman filter")
        self.assertEqual(len(plan.quoted_phrases), 1)
        self.assertEqual(len(plan.identity_probes), 1)
        self.assertEqual(len(plan.metadata_predicates), 1)
        self.assertEqual(plan.mode, SearchMode.STANDARD)
        self.assertEqual(plan.implied_sort, ImpliedSort.RELEVANCE)

    def test_retrieval_candidate_and_channel(self):
        self.assertEqual(RetrievalChannel.IDENTITY.value, "identity")
        self.assertEqual(RetrievalChannel.TITLE_BM25.value, "title_bm25")
        self.assertEqual(RetrievalChannel.CONTENT_BM25.value, "content_bm25")
        self.assertEqual(RetrievalChannel.TITLE_VECTOR.value, "title_vector")
        self.assertEqual(RetrievalChannel.CONTENT_VECTOR.value, "content_vector")
        self.assertEqual(RetrievalChannel.METADATA.value, "metadata")

        candidate = RetrievalCandidate(
            document_id=42,
            channel=RetrievalChannel.CONTENT_BM25,
            score=12.5,
            rank=1,
            chunk_index=3,
            chunk_text="A matching chunk passage",
            metadata={"unit_type": "paragraph"},
        )

        self.assertEqual(candidate.document_id, 42)
        self.assertEqual(candidate.channel, RetrievalChannel.CONTENT_BM25)
        self.assertEqual(candidate.score, 12.5)
        self.assertEqual(candidate.chunk_index, 3)
        self.assertEqual(candidate.metadata["unit_type"], "paragraph")

    def test_search_result_and_evidence(self):
        doc_meta = DocumentMetadata(
            id=42,
            path="/path/to/report.pdf",
            filename="report.pdf",
            extension=".pdf",
            size=1024,
            created_at=1700000000.0,
            modified_at=1700001000.0,
            content_hash="abc123hash",
            processing_status="completed",
        )

        evidence = EvidenceItem(
            evidence_type=EvidenceType.TITLE_LEXICAL,
            description="Title matches query term",
            snippet="Report 2024",
            confidence=0.9,
            source_channel=RetrievalChannel.TITLE_BM25,
        )

        passage = PassageEvidence(
            chunk_index=2,
            text="Sample best passage text",
            score=0.85,
            channel=RetrievalChannel.CONTENT_VECTOR,
        )

        result = SearchResult(
            document_id=42,
            document=doc_meta,
            final_score=0.92,
            identity_tier=IdentityTier.EXACT_FILENAME,
            topical_score=0.88,
            metadata_adjustment=0.04,
            evidence=[evidence],
            passages=[passage],
            channel_ranks={"title_bm25": 1, "content_vector": 2},
            channel_scores={"title_bm25": 15.0, "content_vector": 0.85},
        )

        self.assertEqual(result.document_id, 42)
        self.assertIsNotNone(result.document)
        self.assertEqual(result.document.filename, "report.pdf")
        self.assertEqual(result.identity_tier, IdentityTier.EXACT_FILENAME)
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].evidence_type, EvidenceType.TITLE_LEXICAL)
        self.assertEqual(len(result.passages), 1)
        self.assertEqual(result.passages[0].chunk_index, 2)


if __name__ == "__main__":
    unittest.main()
