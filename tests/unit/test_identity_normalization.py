import unittest

from syami.domain.search import (
    generate_identity_keys,
    normalize_filename_key,
    normalize_path_key,
    normalize_stem_key,
)


class TestIdentityNormalization(unittest.TestCase):

    def test_normalize_filename_key(self):
        self.assertEqual(normalize_filename_key("IAI_Endsem.pdf"), "iai_endsem.pdf")
        self.assertEqual(normalize_filename_key("IAI-Endsem.PDF"), "iai-endsem.pdf")
        self.assertEqual(normalize_filename_key("  My   Report.docx  "), "my report.docx")
        self.assertEqual(normalize_filename_key(""), "")

    def test_normalize_stem_key(self):
        # Treats spaces, underscores, hyphens, and dots consistently
        self.assertEqual(normalize_stem_key("IAI_Endsem"), "iai_endsem")
        self.assertEqual(normalize_stem_key("IAI-Endsem"), "iai_endsem")
        self.assertEqual(normalize_stem_key("IAI Endsem"), "iai_endsem")
        self.assertEqual(normalize_stem_key("iai.endsem"), "iai_endsem")
        self.assertEqual(normalize_stem_key("  My---Report__2024..final  "), "my_report_2024_final")
        self.assertEqual(normalize_stem_key(""), "")

    def test_normalize_path_key(self):
        norm = normalize_path_key("C:\\Users\\User\\Documents\\Report.PDF")
        self.assertIn("c:/users/user/documents/report.pdf", norm.lower())
        self.assertNotIn("\\", norm)
        self.assertEqual(normalize_path_key(""), "")

    def test_generate_identity_keys(self):
        filename_key, stem_key, path_key = generate_identity_keys(
            "C:\\data\\project\\IAI_Endsem.pdf"
        )
        self.assertEqual(filename_key, "iai_endsem.pdf")
        self.assertEqual(stem_key, "iai_endsem")
        self.assertTrue(path_key.endswith("iai_endsem.pdf"))


if __name__ == "__main__":
    unittest.main()
