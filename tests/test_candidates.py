import unittest

from app.nodes.normalize import normalize_fields
from app.services.merge import merge_candidates
from app.nodes.rule_extract import rule_candidates, rule_extract
from app.state import FIELDS


class CandidateTests(unittest.TestCase):
    def test_collects_multiple_bills_and_prefers_bill_over_booking(self):
        source = "Booking No.: 123456789\nB/L NO.: COSU6468631610\n"
        values = rule_extract(source)
        document = {"name": "notice.pdf", "role": "入货通知",
                    "rule_candidates": rule_candidates(source, values)}
        result = merge_candidates([(document, values)])
        self.assertEqual(result["bl_number"]["value"], "COSU6468631610")
        self.assertGreaterEqual(len(result["bl_number"]["candidates"]), 2)

    def test_rejects_impossible_container_quantity(self):
        source = "箱量：330X40GP\n箱型/箱量：7X40RQ\n"
        values = rule_extract(source)
        document = {"name": "notice.pdf", "role": "入货通知",
                    "rule_candidates": rule_candidates(source, values)}
        result = merge_candidates([(document, values)])
        self.assertNotEqual(result["containers"]["value"], "330X40GP")

    def test_low_evidence_port_is_left_blank(self):
        values = {key: {"value": "", "evidence": ""} for key in FIELDS}
        values["origin"] = {"value": "UNKNOWN", "evidence": "UNKNOWN"}
        result = merge_candidates([({"name": "unclear.pdf", "role": "订舱委托书"}, values)])
        self.assertEqual(result["origin"]["value"], "")
        self.assertEqual(result["origin"]["candidates"][0]["value"], "UNKNOWN")

    def test_date_candidate_understands_day_first_year_and_rejects_range(self):
        source = "预计开航/ETD：17.10.2026\n原计划 ETD 10.1-10.7 的船"
        values = rule_extract(source)
        document = {"name": "notice.pdf", "role": "入货通知",
                    "rule_candidates": rule_candidates(source, values)}
        result = merge_candidates([(document, values)])
        self.assertEqual(result["sailing_date"]["value"], "10.17")
        self.assertNotIn("10.1", [item["value"] for item in result["sailing_date"]["candidates"]])

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
