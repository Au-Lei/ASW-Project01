"""Focused ai regression tests, preserved from the original workflow suite."""

import json
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.error import HTTPError, URLError
from io import BytesIO
from unittest.mock import patch
from pathlib import Path
from app.nodes.normalize import normalize_destination, normalize_sailing_date
from app.state import PROJECT_ROOT
from app.tools.ai_extract import ai_extract, build_request, build_chat_request
from app.tools import alias_memory
from app.tools import provider_settings


class AiTests(unittest.TestCase):
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

    def test_ai_sailing_date_and_destination_use_business_display_format(self):
        document = {"name": "入货通知.pdf", "role": "入货通知", "data": b"%PDF-demo", "text": "PROFORMA ETD:08-Sep-2026\n卸货港: HAMAD;QATAR"}
        values = {field: {name: "" for name in ("value", "evidence", "source", "source_label", "review_reason")} for field in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}
        values["sailing_date"].update(value="08-Sep-2026", evidence="PROFORMA ETD:08-Sep-2026", source="入货通知.pdf", source_label="PROFORMA ETD")
        values["destination"].update(value="HAMAD;QATAR", evidence="卸货港: HAMAD;QATAR", source="入货通知.pdf", source_label="卸货港")
        body = {"choices": [{"message": {"content": json.dumps(values, ensure_ascii=False)}}]}
        settings = {"base_url": "https://api.deepseek.com", "api_key": "test-key", "model": "deepseek-chat"}
        with patch("app.tools.ai_extract.get_settings", return_value=settings), patch("app.tools.ai_extract.call_service", return_value=body):
            fields, _ = ai_extract([document])
        self.assertEqual(fields["sailing_date"]["value"], "9.8")
        self.assertEqual(fields["destination"]["value"], "HAMAD")
        self.assertIn("08-Sep-2026", fields["sailing_date"]["evidence"])
        self.assertIn("HAMAD;QATAR", fields["destination"]["evidence"])
        self.assertEqual(normalize_sailing_date("2026-09-08"), "9.8")
        self.assertEqual(normalize_destination("PORT KLANG WEST, MALAYSIA"), "PORT KLANG WEST")
        self.assertEqual(normalize_destination("BELAWAN, SUMATRA"), "BELAWAN, SUMATRA")

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

    def test_auth_failure_does_not_echo_provider_key_fragment(self):
        settings = provider_settings.validate_fields("https://api.deepseek.com", "secret-test-key", "deepseek-flash")
        body = BytesIO(b'{"error":{"message":"Your api key: ****-key is invalid"}}')
        error = HTTPError("https://api.deepseek.com/chat/completions", 401, "Unauthorized", {}, body)
        with patch.object(provider_settings, "urlopen", side_effect=error):
            with self.assertRaises(ValueError) as caught:
                provider_settings.call_service(settings, {"model": "deepseek-flash"})
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertNotIn("****-key", str(caught.exception))

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
