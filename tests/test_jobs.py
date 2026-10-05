"""Focused jobs regression tests, preserved from the original workflow suite."""

import json
import time
import unittest
from unittest.mock import patch
from app import jobs
from app.tools.document_reader import read_document


class JobsTests(unittest.TestCase):
    def test_live_job_reports_real_steps_and_updates_stats(self):
        before = jobs.get_stats()
        document = [{"name": "入货通知.pdf", "role": "入货通知", "data": b"demo"}]
        with patch("app.graph.read_document", return_value="提单号: DEMO12345\n装货港: QINGDAO\n目的港: JAKARTA"):
            job_id = jobs.start_job(document, "rules")
            deadline = time.monotonic() + 2
            while jobs.get_job(job_id)["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
        final = jobs.get_job(job_id)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["result"]["fields"]["bl_number"]["value"], "DEMO12345")
        self.assertEqual(set(event["stage"] for event in final["events"]), set(jobs.STAGES))
        self.assertGreaterEqual(final["elapsed_ms"], 0)
        after = jobs.get_stats()
        self.assertEqual(after["completed"], before["completed"] + 1)
        self.assertGreater(after["filled_fields"], before["filled_fields"])

    def test_failed_job_records_failure_without_document_content_in_stats(self):
        before = jobs.get_stats()
        with patch("app.graph.read_document", side_effect=ValueError("损坏的单据")):
            job_id = jobs.start_job([{"name": "bad.pdf", "role": "入货通知", "data": b"broken"}], "rules")
            deadline = time.monotonic() + 2
            while jobs.get_job(job_id)["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(jobs.get_job(job_id)["status"], "failed")
        self.assertEqual(jobs.get_stats()["failed"], before["failed"] + 1)
        self.assertNotIn("bad.pdf", json.dumps(jobs.get_stats()))
