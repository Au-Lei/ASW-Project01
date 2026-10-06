import unittest

from app.nodes.normalize import normalize_fields
from app.services.merge import merge_candidates
from app.state import FIELDS


class CandidateTests(unittest.TestCase):
    def test_conflicting_document_values_are_kept_for_review(self):
        notice = {key: {"value": "", "evidence": ""} for key in FIELDS}
        entrustment = {key: {"value": "", "evidence": ""} for key in FIELDS}
        notice["destination"] = {"value": "ITGOA", "evidence": "目的港：ITGOA"}
        entrustment["destination"] = {"value": "SAVONA", "evidence": "目的港：SAVONA"}
        result = normalize_fields(merge_candidates([
            ({"name": "notice.pdf", "role": "入货通知"}, notice),
            ({"name": "entrustment.docx", "role": "订舱委托书"}, entrustment),
        ]))
        self.assertEqual(result["destination"]["value"], "GENOVA")
        self.assertTrue(result["destination"]["conflict"])
        self.assertEqual([candidate["value"] for candidate in result["destination"]["candidates"]],
                         ["GENOVA", "SAVONA"])
        self.assertEqual(result["destination"]["candidates"][1]["source"], "entrustment.docx")


if __name__ == "__main__":
    unittest.main()
