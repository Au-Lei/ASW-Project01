import unittest

from app.services.extraction import run_pipeline
from app.nodes.rule_extract import rule_extract
from app.tools.text_quality import assess_text_quality


class TextQualityTests(unittest.TestCase):
    def test_empty_scan_is_flagged(self):
        state, warning = assess_text_quality("scan.pdf", "  ")
        self.assertEqual(state, "little_text")
        self.assertIn("OCR", warning)

    def test_garbled_pdf_is_flagged_without_echoing_content(self):
        state, warning = assess_text_quality("notice.pdf", "Customer private text " * 10 + "\ufffd" * 12)
        self.assertEqual(state, "garbled")
        self.assertNotIn("Customer private text", warning)

    def test_readable_text_is_not_flagged(self):
        self.assertEqual(assess_text_quality("notice.pdf", "Port of Discharge: VANCOUVER\nETD: 2026-10-12"), ("ok", ""))

    def test_pipeline_exposes_quality_warning(self):
        result = run_pipeline(
            [{"name": "scan.pdf", "role": "入货通知", "data": b"placeholder"}],
            "rules", reader=lambda name, data: "", rule_engine=rule_extract, ai_engine=None,
        )
        self.assertEqual(result["documents"][0]["text_quality"], "little_text")
        self.assertIn("OCR", result["warnings"][0])


if __name__ == "__main__":
    unittest.main()
