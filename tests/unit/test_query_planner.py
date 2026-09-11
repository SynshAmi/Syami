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


if __name__ == "__main__":
    unittest.main()
