"""Exercise the production WSGI entry point without network or customer data."""

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import security
from app.wsgi import app


class WSGITests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".runtime_tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        root = Path(self.tmp.name)
        self.db_patch = patch.object(security, "DB_PATH", root / "security.sqlite3")
        self.key_patch = patch.object(security, "KEY_PATH", root / "security.key")
        self.db_patch.start()
        self.key_patch.start()
        security.create_user("alice", "strong-password-alice")
        security.create_user("bob", "strong-password-bob--")
        self.client = app.test_client()

    def tearDown(self):
        self.key_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def login(self, client, username="alice", password="strong-password-alice"):
        response = client.post("/api/login", json={"username": username, "password": password},
                               headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Secure", response.headers["Set-Cookie"])
        return response.json["csrf"]

    def test_session_csrf_logout_and_private_routes(self):
        self.assertEqual(self.client.get("/api/stats").status_code, 401)
        self.login(self.client)
        current = self.client.get("/api/session").json
        self.assertTrue(current["authenticated"])
        csrf = current["csrf"]
        self.assertEqual(self.client.post("/api/export", json={"values": {}}).status_code, 403)
        self.assertEqual(self.client.post("/api/logout", json={}, headers={"X-CSRF-Token": csrf}).status_code, 200)
        self.assertEqual(self.client.get("/api/stats").status_code, 401)

    def test_extract_review_export_and_cross_user_job(self):
        csrf = self.login(self.client)
        with patch("app.jobs.extract", return_value={"fields": {key: {"value": ""} for key in __import__("app.state", fromlist=["FIELDS"]).FIELDS}}):
            response = self.client.post("/api/extract/start", json={"mode": "rules", "documents": [
                {"name": "test.rtf", "role": "入货通知", "data": base64.b64encode(b"{\\rtf1\\ansi sample}").decode()}
            ]}, headers={"X-CSRF-Token": csrf})
            self.assertEqual(response.status_code, 202, response.json)
            job_id = response.json["job_id"]
            self.assertEqual(self.client.get("/api/extract/status?job_id=" + job_id).status_code, 200)
        export = self.client.post("/api/export", json={"values": {"bill_no": "TEST123"}}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(export.status_code, 200, export.json if export.is_json else "")
        self.assertTrue(export.data.startswith(b"PK"))
        other = app.test_client()
        self.login(other, "bob", "strong-password-bob--")
        self.assertEqual(other.get("/api/extract/status?job_id=" + job_id).status_code, 404)

    def test_origin_content_type_and_server_setup_lock(self):
        with patch.dict("os.environ", {"ASW_REQUIRE_EXTERNAL_KEY": "1"}):
            self.assertEqual(self.client.post("/api/setup", json={"username": "x", "password": "x"}).status_code, 403)
        response = self.client.post("/api/login", data="{}", content_type="text/plain")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/login", json={"username": "alice", "password": "strong-password-alice"},
                                    headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)

    def test_serve_trusts_only_local_proxy_proto(self):
        from app.wsgi import serve
        with patch("app.wsgi._cipher"), patch("waitress.serve") as waitress_serve:
            serve(9876)
        options = waitress_serve.call_args.kwargs
        self.assertEqual(options["host"], "127.0.0.1")
        self.assertEqual(options["trusted_proxy"], "127.0.0.1")
        self.assertEqual(options["trusted_proxy_headers"], "x-forwarded-proto")


if __name__ == "__main__":
    unittest.main()
