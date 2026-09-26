"""Focused regression checks for the demo workflow."""

import io
import json
import os
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.error import URLError
from unittest.mock import patch
from pathlib import Path
from subprocess import CompletedProcess

import openpyxl

from app.graph import extract
from app import jobs
from app.nodes.rule_extract import rule_extract
from app.nodes.normalize import normalize_origin
from app.tools.excel_export import make_workbook
from app.tools.document_reader import read_document
from app.state import PROJECT_ROOT
from app.tools.ai_extract import ai_extract, build_request, build_chat_request
from app.tools import alias_memory
from app.tools import provider_settings


class WorkflowTests(unittest.TestCase):
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

    def test_ai_request_includes_word_layout_and_approved_alias(self):
        documents = [{"name": "入货通知.doc", "role": "入货通知", "data": b"word bytes", "text": "D/R No. (编号)\n177CWWZUQ0455"}]
        with patch("app.tools.ai_extract.word_to_pdf", return_value=b"%PDF-demo"):
            payload, warnings = build_request(documents)
        content = payload["input"][0]["content"]
        files = [part for part in content if part["type"] == "input_file"]
        self.assertEqual(warnings, [])
        self.assertEqual(files[0]["filename"], "入货通知.pdf")
        self.assertEqual(files[0]["detail"], "high")
        self.assertIn("D/R No.", content[1]["text"])
        self.assertIn("source_label", payload["text"]["format"]["schema"]["properties"]["bl_number"]["properties"])

    def test_ai_response_keeps_source_label_for_review(self):
        document = {"name": "入货通知.pdf", "role": "入货通知", "data": b"%PDF-demo", "text": "D/R No. 177CWWZUQ0455"}
        values = {field: {"value": "", "evidence": "", "source": "", "source_label": "", "review_reason": ""} for field in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}
        values["bl_number"] = {"value": "177CWWZUQ0455", "evidence": "D/R No. 177CWWZUQ0455", "source": "入货通知.pdf", "source_label": "D/R No.", "review_reason": ""}
        body = {"output": [{"content": [{"type": "output_text", "text": json.dumps(values)}]}]}
        settings = {"base_url": "https://api.openai.com/v1", "api_key": "test-key", "model": "gpt-4.1-mini"}
        with patch("app.tools.ai_extract.get_settings", return_value=settings), patch("app.tools.ai_extract.call_service", return_value=body):
            fields, warnings = ai_extract([document])
        self.assertEqual(warnings, [])
        self.assertEqual(fields["bl_number"]["value"], "177CWWZUQ0455")
        self.assertEqual(fields["bl_number"]["source_label"], "D/R No.")

    def test_page_settings_are_runtime_only_and_never_return_key(self):
        try:
            with patch.object(provider_settings, "call_service", return_value={"choices": [{"message": {"content": "{\"ok\":true}"}}]}) as probe:
                provider_settings.test_and_save("https://api.deepseek.com/", "temporary-secret", "deepseek-chat")
            self.assertEqual(probe.call_args.args[0]["base_url"], "https://api.deepseek.com")
            public = provider_settings.public_settings()
            self.assertTrue(public["ai_available"])
            self.assertEqual(public["base_url"], "https://api.deepseek.com")
            self.assertNotIn("api_key", public)
            self.assertNotIn("temporary-secret", json.dumps(public))
            provider_settings.clear_settings()
            self.assertFalse(provider_settings.public_settings()["ai_available"])
        finally:
            provider_settings.clear_settings()

    def test_failed_connection_does_not_enable_ai(self):
        provider_settings.clear_settings()
        with patch.object(provider_settings, "call_service", side_effect=ValueError("无法连接 AI 服务")):
            with self.assertRaisesRegex(ValueError, "无法连接"):
                provider_settings.test_and_save("https://api.deepseek.com", "test-secret", "deepseek-chat")
        self.assertFalse(provider_settings.public_settings()["ai_available"])
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            provider_settings.normalize_base_url("http://example.com/v1")
        self.assertEqual(provider_settings.endpoint("https://api.openai.com/v1"), "https://api.openai.com/v1/responses")
        self.assertEqual(provider_settings.endpoint("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")

    def test_refused_proxy_error_identifies_proxy_without_leaking_key(self):
        settings = provider_settings.validate_fields("https://api.deepseek.com", "secret-test-key", "deepseek-flash")
        with patch.object(provider_settings, "urlopen", side_effect=URLError("[WinError 10061] connection refused")), patch.object(provider_settings, "getproxies", return_value={"https": "http://user:password@127.0.0.1:9"}):
            with self.assertRaises(ValueError) as caught:
                provider_settings.call_service(settings, {"model": "deepseek-flash"})
        self.assertIn("127.0.0.1:9", str(caught.exception))
        self.assertNotIn("password", str(caught.exception))
        self.assertNotIn("secret-test-key", str(caught.exception))

    def test_connection_probe_reaches_local_compatible_service(self):
        seen = []

        class FakeHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))) )
                body = b'{"id":"chatcmpl-local","choices":[{"message":{"content":"{\\\"ok\\\":true}"}}]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), FakeHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}/v1"
            provider_settings.test_and_save(base_url, "local-test-key", "demo-model")
            self.assertEqual(seen[0][0], "/v1/chat/completions")
            self.assertEqual(seen[0][1], "Bearer local-test-key")
            self.assertEqual(seen[0][2]["model"], "demo-model")
        finally:
            provider_settings.clear_settings()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_deepseek_uses_text_json_and_configured_model(self):
        document = {"name": "入货通知.doc", "role": "入货通知", "data": b"word bytes", "text": "D/R No. 177CWWZUQ0455"}
        request, warnings = build_chat_request([document], "deepseek-chat")
        self.assertEqual(request["model"], "deepseek-chat")
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertIn("177CWWZUQ0455", request["messages"][0]["content"])
        self.assertTrue(warnings)
        values = {field: {name: "" for name in ("value", "evidence", "source", "source_label", "review_reason")} for field in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}
        values["bl_number"] = {"value": "177CWWZUQ0455", "evidence": "D/R No. 177CWWZUQ0455", "source": "入货通知.doc", "source_label": "D/R No.", "review_reason": ""}
        body = {"choices": [{"message": {"content": json.dumps(values)}}]}
        try:
            with patch.object(provider_settings, "call_service", return_value={"choices": [{"message": {"content": "{\"ok\":true}"}}]}):
                provider_settings.test_and_save("https://api.deepseek.com", "temporary-secret", "deepseek-chat")
            with patch("app.tools.ai_extract.call_service", return_value=body) as send:
                fields, _ = ai_extract([document])
            self.assertEqual(provider_settings.endpoint(send.call_args.args[0]["base_url"]), "https://api.deepseek.com/chat/completions")
            self.assertEqual(fields["bl_number"]["value"], "177CWWZUQ0455")
        finally:
            provider_settings.clear_settings()

    def test_memory_saves_only_confirmed_alias_labels(self):
        temporary_root = PROJECT_ROOT / ".runtime_tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=temporary_root, suffix=".json", delete=False) as memory_file:
            memory_file.write('{"bl_number": ["D/R No."]}')
            path = Path(memory_file.name)
        try:
            with patch.object(alias_memory, "MEMORY_FILE", path):
                added = alias_memory.remember_aliases([{"field": "bl_number", "source_label": "Document Receipt No."}])
                self.assertEqual(added, 1)
                self.assertEqual(alias_memory.remember_aliases([{"field": "bl_number", "source_label": "Document Receipt No."}]), 0)
                self.assertIn("Document Receipt No.", alias_memory.load_aliases()["bl_number"])
                self.assertNotIn("177CWWZUQ0455", path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)

    def test_each_single_document_is_extracted_without_prior_shipment(self):
        first = [{"name": "A委托书.pdf", "role": "订舱委托书", "data": b"first"}]
        second = [{"name": "B入货通知.pdf", "role": "入货通知", "data": b"second"}]
        with patch("app.graph.read_document", side_effect=["提单号: FIRST12345\n装货港: QINGDAO", "提单号: SECOND67890\n目的港: PORT KLANG WEST"]):
            first_result = extract(first, "rules")
            second_result = extract(second, "rules")
        self.assertEqual(first_result["fields"]["bl_number"]["value"], "FIRST12345")
        self.assertEqual(first_result["fields"]["origin"]["value"], "QD")
        self.assertEqual(second_result["fields"]["bl_number"]["value"], "SECOND67890")
        self.assertEqual(second_result["fields"]["destination"]["value"], "PORT KLANG WEST")
        self.assertEqual(second_result["fields"]["origin"]["value"], "")
        self.assertEqual(len(second_result["documents"]), 1)

    def test_two_column_notice_keeps_fields_separate(self):
        notice = (
            "船名/航次: XIN QIN HUANG DAO/135S   提单号: COAU9509489770\n"
            "装货港: QINGDAO, CHINA   目的港: PORT KLANG WEST\n"
            "船期: 2026/9/13   箱量: 40HC*1\n"
            "场站: 神州行场站"
        )
        fields = rule_extract(notice)
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "COAU9509489770", "vessel": "XIN QIN HUANG DAO", "voyage": "135S", "sailing_date": "9.13",
            "containers": "1X40HC", "station": "神州行场站", "destination": "PORT KLANG WEST", "origin": "QINGDAO, CHINA",
        })

    def test_destination_can_follow_another_field_without_separator(self):
        fields = rule_extract("装货港: QINGDAO,CHINA目的港: PORT KLANG WEST\n目 的 港：PORT KLANG WEST")
        self.assertEqual(fields["destination"]["value"], "PORT KLANG WEST")

    def test_domestic_origin_uses_company_abbreviation(self):
        self.assertEqual(normalize_origin("QINGDAO, CHINA"), "QD")
        self.assertEqual(normalize_origin("TIANJIN XINGANG"), "TJ")
        self.assertEqual(normalize_origin("PORT KLANG"), "PORT KLANG")

    def test_legacy_reader_uses_writable_project_temp_file(self):
        seen = []

        def fake_office(command, **kwargs):
            source = Path(command[-1])
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"legacy sample")
            self.assertEqual(source.parent, PROJECT_ROOT / ".runtime_tmp")
            seen.append(source)
            return CompletedProcess(command, 0, "提单号: TEST123456\n", "")

        with patch("app.tools.document_reader.subprocess.run", side_effect=fake_office):
            self.assertIn("TEST123456", read_document("test.xls", b"legacy sample"))
        self.assertFalse(seen[0].exists())

    def test_notice_wins_and_conflict_is_visible(self):
        entrust = "PORT OF LOADING: QINGDAO\nPORT OF DISCHARGE: JAKARTA\n2X40HQ"
        notice = "BOOKING NUMBER : 2339673950\nETD : 14 Oct 2026\nDESPATCH QUANTITY FCL QTY : 3 X 40HQ"
        documents = [{"name": "委托书.pdf", "role": "订舱委托书", "data": b"first"}, {"name": "入货通知.pdf", "role": "入货通知", "data": b"second"}]
        with patch("app.graph.read_document", side_effect=[entrust, notice]):
            result = extract(documents, "rules")
        self.assertEqual(result["fields"]["sailing_date"]["value"], "10.14")
        self.assertEqual(result["fields"]["containers"]["value"], "3X40HQ")
        self.assertTrue(result["fields"]["containers"]["conflict"])
        self.assertEqual(result["fields"]["containers"]["source"], "入货通知.pdf")
        self.assertEqual(result["fields"]["origin"]["value"], "QD")

    def test_export_preserves_template_and_blank_manual_fields(self):
        workbook = openpyxl.load_workbook(io.BytesIO(make_workbook({"bl_number": "2339673950", "vessel": "CMA CGM FORT DIAMANT", "sailing_date": "10.14"})))
        sheet = workbook["业务联系单"]
        self.assertEqual(sheet["B8"].value, "2339673950")
        self.assertEqual(sheet["B9"].value, "CMA CGM FORT DIAMANT")
        self.assertEqual(sheet["B10"].value, "10.14")
        self.assertIsNone(sheet["B4"].value)
        self.assertIsNone(sheet["E3"].value)
        self.assertEqual(sheet["A1"].value, "港捷物流业务联系单")


if __name__ == "__main__":
    unittest.main()
