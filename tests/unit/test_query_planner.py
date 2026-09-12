from datetime import datetime
import unittest

from syami.application.search.planning import QueryPlanner, plan_query
from syami.domain.search import (
    IdentityKind,
    ImpliedSort,
    MetadataConfidence,
    MetadataEnforcement,
    MetadataPrecision,
    SearchMode,
)


class TestQueryPlanner(unittest.TestCase):

    def setUp(self):
        # Anchor reference time to 2026-09-12 12:00:00 UTC (Saturday)
        self.ref_time = datetime(2026, 9, 12, 12, 0, 0).timestamp()
        self.planner = QueryPlanner(reference_time=self.ref_time)

    def test_empty_and_whitespace_queries(self):
        plan_empty = self.planner.plan("")
        self.assertEqual(plan_empty.original_text, "")
        self.assertIsNone(plan_empty.topical_text)
        self.assertIn("Empty search query", plan_empty.diagnostics)

        plan_ws = self.planner.plan("   \t\n  ")
        self.assertEqual(plan_ws.normalized_text, "")
        self.assertIsNone(plan_ws.topical_text)

    def test_plain_topical_query(self):
        plan = self.planner.plan("Kalman filter algorithm")
        self.assertEqual(plan.original_text, "Kalman filter algorithm")
        self.assertIn("Kalman filter algorithm", plan.topical_text)
        self.assertEqual(len(plan.identity_probes), 0)
        self.assertEqual(len(plan.metadata_predicates), 0)
        self.assertEqual(plan.mode, SearchMode.STANDARD)

    def test_exact_filename_query(self):
        plan = self.planner.plan("Transformers Notes.pdf")
        self.assertEqual(len(plan.identity_probes), 2)
        fn_probe = next(p for p in plan.identity_probes if p.kind == IdentityKind.FILENAME)
        stem_probe = next(p for p in plan.identity_probes if p.kind == IdentityKind.STEM)
        self.assertEqual(fn_probe.normalized_value, "transformers notes.pdf")
        self.assertEqual(stem_probe.normalized_value, "transformers_notes")

    def test_stem_like_identity_query(self):
        plan = self.planner.plan("IAI_Endsem")
        self.assertEqual(len(plan.identity_probes), 1)
        self.assertEqual(plan.identity_probes[0].kind, IdentityKind.STEM)
        self.assertEqual(plan.identity_probes[0].normalized_value, "iai_endsem")

    def test_path_like_query(self):
        plan = self.planner.plan("C:/projects/syami/notes.md")
        path_probe = next(p for p in plan.identity_probes if p.kind == IdentityKind.PATH)
        self.assertIn("c:/projects/syami/notes.md", path_probe.normalized_value)
        self.assertEqual(path_probe.specificity, 1.0)

    def test_quoted_phrases_extraction(self):
        plan = self.planner.plan('find documents containing "Kalman filter" and "state estimation"')
        self.assertIn("Kalman filter", plan.quoted_phrases)
        self.assertIn("state estimation", plan.quoted_phrases)
        self.assertEqual(len(plan.quoted_phrases), 2)

    def test_explicit_mandatory_metadata_predicate(self):
        plan = self.planner.plan("only PDFs about robotics")
        self.assertEqual(len(plan.metadata_predicates), 1)
        pred = plan.metadata_predicates[0]
        self.assertEqual(pred.field, "extension")
        self.assertEqual(pred.canonical_value, ".pdf")
        self.assertEqual(pred.confidence, MetadataConfidence.HIGH)
        self.assertEqual(pred.enforcement, MetadataEnforcement.MANDATORY)
        self.assertIn("robotics", plan.topical_text.lower())

    def test_standard_strict_preferred_metadata_predicate(self):
        plan = self.planner.plan("PDF about transformers")
        self.assertEqual(len(plan.metadata_predicates), 1)
        pred = plan.metadata_predicates[0]
        self.assertEqual(pred.field, "extension")
        self.assertEqual(pred.canonical_value, ".pdf")
        self.assertEqual(pred.confidence, MetadataConfidence.MEDIUM)
        self.assertEqual(pred.enforcement, MetadataEnforcement.STRICT_PREFERRED)
        self.assertIn("transformers", plan.topical_text.lower())

    def test_hedged_low_confidence_metadata_predicate(self):
        plan = self.planner.plan("I think it was a Word document about deep learning")
        self.assertEqual(len(plan.metadata_predicates), 1)
        pred = plan.metadata_predicates[0]
        self.assertEqual(pred.field, "extension")
        self.assertEqual(pred.canonical_value, ".docx")
        self.assertEqual(pred.confidence, MetadataConfidence.LOW)
        self.assertEqual(pred.enforcement, MetadataEnforcement.SOFT_ONLY)

    def test_date_metadata_yesterday(self):
        plan = self.planner.plan("files modified yesterday")
        date_preds = [p for p in plan.metadata_predicates if p.field == "modified_at"]
        self.assertEqual(len(date_preds), 1)
        self.assertEqual(date_preds[0].operator, "between")
        self.assertEqual(date_preds[0].confidence, MetadataConfidence.MEDIUM)
        self.assertEqual(plan.mode, SearchMode.METADATA_DOMINANT)
        self.assertEqual(plan.implied_sort, ImpliedSort.RECENCY)

    def test_date_metadata_last_year(self):
        plan = self.planner.plan("files modified last year")
        date_preds = [p for p in plan.metadata_predicates if p.field == "modified_at"]
        self.assertEqual(len(date_preds), 1)
        pred = date_preds[0]
        self.assertEqual(pred.operator, "between")
        expected_start = datetime(2025, 1, 1).timestamp()
        expected_end = datetime(2026, 1, 1).timestamp()
        self.assertEqual(pred.canonical_value, (expected_start, expected_end))
        self.assertEqual(pred.confidence, MetadataConfidence.MEDIUM)
        self.assertEqual(pred.enforcement, MetadataEnforcement.STRICT_PREFERRED)
        self.assertEqual(len(plan.diagnostics), 0)
        self.assertIsNone(plan.topical_text)
        self.assertEqual(plan.mode, SearchMode.METADATA_DOMINANT)
        self.assertEqual(plan.implied_sort, ImpliedSort.RECENCY)

    def test_unresolved_temporal_language_diagnostics(self):
        plan = self.planner.plan("exam notes from last semester")
        self.assertEqual(len([p for p in plan.metadata_predicates if p.field == "modified_at"]), 0)
        self.assertTrue(any("last semester" in d for d in plan.diagnostics))
        self.assertIsNotNone(plan.topical_text)

    def test_size_predicates(self):
        plan = self.planner.plan("PDFs larger than 10MB")
        size_preds = [p for p in plan.metadata_predicates if p.field == "size"]
        self.assertEqual(len(size_preds), 1)
        self.assertEqual(size_preds[0].operator, "gte")
        self.assertEqual(size_preds[0].canonical_value, 10 * 1024 * 1024)

    def test_location_folder_predicate(self):
        plan = self.planner.plan("the notes in my ML folder")
        loc_preds = [p for p in plan.metadata_predicates if p.field == "path_prefix"]
        self.assertEqual(len(loc_preds), 1)
        self.assertEqual(loc_preds[0].canonical_value, "ml")

    def test_metadata_dominant_mode(self):
        plan = self.planner.plan("only PDFs")
        self.assertEqual(plan.mode, SearchMode.METADATA_DOMINANT)
        self.assertIsNone(plan.topical_text)

    def test_recent_browsing_mode(self):
        plan = self.planner.plan("show recent files")
        self.assertEqual(plan.mode, SearchMode.RECENT)
        self.assertEqual(plan.implied_sort, ImpliedSort.RECENCY)

    def test_deterministic_output_for_identical_input(self):
        query = "find the Kalman filter PDF modified yesterday"
        plan1 = self.planner.plan(query)
        plan2 = self.planner.plan(query)
        self.assertEqual(plan1, plan2)

    # -------------------------------------------------------------
    # 10 Focused Planner Requirement Tests
    # -------------------------------------------------------------

    def test_req1_broad_topic_plus_one_remembered_question(self):
        """1. Broad topic + one remembered question."""
        query = "distributed systems notes mentioning 'how does Paxos consensus work'"
        plan = self.planner.plan(query)
        self.assertEqual(plan.topical_text, "distributed systems")
        self.assertEqual(plan.semantic_text, "distributed systems")
        self.assertEqual(plan.quoted_phrases, ["how does Paxos consensus work"])
        self.assertEqual(len(plan.identity_probes), 0)
        self.assertEqual(len(plan.metadata_predicates), 0)

    def test_req2_broad_topic_plus_multiple_remembered_questions(self):
        """2. Broad topic + multiple remembered questions."""
        query = "Machine learning guide with 'what is gradient descent' and 'explain backpropagation'"
        plan = self.planner.plan(query)
        self.assertEqual(plan.topical_text, "Machine learning guide")
        self.assertEqual(plan.semantic_text, "Machine learning guide")
        self.assertEqual(
            plan.quoted_phrases,
            ["what is gradient descent", "explain backpropagation"],
        )
        self.assertEqual(len(plan.identity_probes), 0)
        self.assertEqual(len(plan.metadata_predicates), 0)

    def test_req3_pdf_metadata_topic_multiple_clues(self):
        """3. PDF metadata + topic + multiple clues."""
        query = "PDF on database internals mentioning 'b-tree index' and 'write-ahead logging'"
        plan = self.planner.plan(query)
        self.assertEqual(len(plan.metadata_predicates), 1)
        self.assertEqual(plan.metadata_predicates[0].field, "extension")
        self.assertEqual(plan.metadata_predicates[0].canonical_value, ".pdf")
        self.assertEqual(plan.topical_text, "database internals")
        self.assertEqual(plan.semantic_text, "database internals")
        self.assertEqual(
            plan.quoted_phrases,
            ["b-tree index", "write-ahead logging"],
        )
        self.assertEqual(len(plan.identity_probes), 0)

    def test_req4_pure_topical_query_no_clues(self):
        """4. Pure topical query with no remembered clues."""
        query = "Kalman filter state estimation algorithm"
        plan = self.planner.plan(query)
        self.assertEqual(plan.topical_text, "Kalman filter state estimation algorithm")
        self.assertEqual(plan.semantic_text, "Kalman filter state estimation algorithm")
        self.assertEqual(plan.quoted_phrases, [])
        self.assertEqual(len(plan.identity_probes), 0)
        self.assertEqual(len(plan.metadata_predicates), 0)
        self.assertEqual(plan.mode, SearchMode.STANDARD)

    def test_req5_query_containing_only_remembered_questions(self):
        """5. Query containing only remembered questions."""
        query = "Find documents containing 'what is IOC in Spring'"
        plan = self.planner.plan(query)
        self.assertEqual(plan.topical_text, "what is IOC in Spring")
        self.assertEqual(plan.semantic_text, "what is IOC in Spring")
        self.assertEqual(plan.quoted_phrases, ["what is IOC in Spring"])
        self.assertEqual(len(plan.identity_probes), 0)

    def test_req6_date_filetype_metadata_mixed_with_topic(self):
        """6. Date/file-type metadata mixed with topical text."""
        query = "PDF modified yesterday about quantum computing"
        plan = self.planner.plan(query)
        ext_preds = [p for p in plan.metadata_predicates if p.field == "extension"]
        date_preds = [p for p in plan.metadata_predicates if p.field == "modified_at"]
        self.assertEqual(len(ext_preds), 1)
        self.assertEqual(ext_preds[0].canonical_value, ".pdf")
        self.assertEqual(len(date_preds), 1)
        self.assertEqual(date_preds[0].operator, "between")
        self.assertEqual(plan.topical_text, "quantum computing")
        self.assertEqual(plan.semantic_text, "quantum computing")
        self.assertEqual(len(plan.identity_probes), 0)

    def test_req7_duplicate_remembered_clues(self):
        """7. Duplicate remembered clues."""
        query = "Python tutorial mentioning 'list comprehension' and 'list comprehension'"
        plan = self.planner.plan(query)
        self.assertEqual(plan.topical_text, "Python tutorial")
        self.assertEqual(plan.semantic_text, "Python tutorial")
        self.assertEqual(plan.quoted_phrases, ["list comprehension"])

    def test_req8_quoted_clues_punctuation_and_capitalization_differences(self):
        """8. Quoted clues with punctuation and capitalization differences."""
        query = "Guide with 'What is Dependency Injection?' and 'what is dependency injection?'"
        plan = self.planner.plan(query)
        self.assertEqual(plan.topical_text, "Guide")
        self.assertEqual(plan.semantic_text, "Guide")
        # Deduplication case-insensitively preserves the first occurrence
        self.assertEqual(plan.quoted_phrases, ["What is Dependency Injection?"])

    def test_req9_identity_only_query_no_semantic_text(self):
        """9. Identity-only query, ensuring semantic_text does not become the filename/path."""
        plan_fn = self.planner.plan("Transformers Notes.pdf")
        self.assertEqual(plan_fn.mode, SearchMode.IDENTITY_DOMINANT)
        self.assertIsNone(plan_fn.topical_text)
        self.assertIsNone(plan_fn.semantic_text)
        self.assertTrue(len(plan_fn.identity_probes) > 0)

        plan_path = self.planner.plan("C:/docs/report.pdf")
        self.assertEqual(plan_path.mode, SearchMode.IDENTITY_DOMINANT)
        self.assertIsNone(plan_path.topical_text)
        self.assertIsNone(plan_path.semantic_text)
        self.assertTrue(len(plan_path.identity_probes) > 0)

    def test_req10_java_top_50_interview_questions_canonical_example(self):
        """10. The existing 'Java top 50 interview questions' example."""
        query = (
            "Find the PDF in which content was about Java top 50 interview questions. "
            "It had some questions about 'what is IOC in Spring', 'what is dependency injection', "
            "and 'what is the difference between JDK, JRE and JVM'."
        )
        plan = self.planner.plan(query)

        # Metadata
        ext_preds = [p for p in plan.metadata_predicates if p.field == "extension"]
        self.assertEqual(len(ext_preds), 1)
        self.assertEqual(ext_preds[0].canonical_value, ".pdf")

        # Broad topical and semantic text
        self.assertEqual(plan.topical_text, "Java top 50 interview questions")
        self.assertEqual(plan.semantic_text, "Java top 50 interview questions")

        # Quoted lexical clues
        self.assertEqual(
            plan.quoted_phrases,
            [
                "what is IOC in Spring",
                "what is dependency injection",
                "what is the difference between JDK, JRE and JVM",
            ],
        )

        # Identity probes: none for this query
        self.assertEqual(len(plan.identity_probes), 0)

        # Mode
        self.assertEqual(plan.mode, SearchMode.STANDARD)

        # Smart quotes test version of the same query
        query_smart = (
            "Find the PDF in which content was about Java top 50 interview questions. "
            "It had some questions about ‘what is IOC in Spring’, ‘what is dependency injection’, "
            "and ‘what is the difference between JDK, JRE and JVM’."
        )
        plan_smart = self.planner.plan(query_smart)
        self.assertEqual(plan_smart.topical_text, "Java top 50 interview questions")
        self.assertEqual(plan_smart.semantic_text, "Java top 50 interview questions")
        self.assertEqual(
            plan_smart.quoted_phrases,
            [
                "what is IOC in Spring",
                "what is dependency injection",
                "what is the difference between JDK, JRE and JVM",
            ],
        )


if __name__ == "__main__":
    unittest.main()
