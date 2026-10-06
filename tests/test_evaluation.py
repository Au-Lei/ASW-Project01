import unittest

from app.evaluation import score_case, summarize_cases
from app.state import FIELDS


class EvaluationTests(unittest.TestCase):
    def test_separates_correct_blank_missing_and_wrong_value(self):
        expected = {key: "" for key in FIELDS}
        expected.update({"bl_number": "BL123", "vessel": "TEST SHIP", "voyage": "001W"})
        actual = {"bl_number": {"value": "bl123"}, "vessel": {"value": ""},
                  "voyage": {"value": "002W"}, "station": {"value": ""}}
        report = score_case(expected, actual)
        self.assertEqual(report["fields"]["bl_number"]["status"], "correct")
        self.assertEqual(report["fields"]["vessel"]["status"], "missed")
        self.assertEqual(report["fields"]["voyage"]["status"], "wrong_value")
        self.assertEqual(report["fields"]["station"]["status"], "correct_blank")
        self.assertFalse(report["all_correct"])
        self.assertEqual(summarize_cases([report])["fields"]["wrong_value"], 1)

    def test_rejects_incomplete_gold(self):
        with self.assertRaises(ValueError):
            score_case({"bl_number": "BL123"}, {})


if __name__ == "__main__":
    unittest.main()
