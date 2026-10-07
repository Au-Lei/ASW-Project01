"""Task 5 security boundaries, without real customer files or API keys."""

import io
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from threading import Thread
from urllib.request import ProxyHandler, Request, build_opener
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import security
from app.jobs import get_job, start_job
from app.services.requests import decode_extraction_request
from app.tools import alias_memory, provider_settings
from scripts.backup_data import backup
from app.web import Handler


class SecurityTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".runtime_tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.tmp.name)
        self.patches = [patch.object(security, "DB_PATH", self.root / "security.sqlite3"),
                        patch.object(security, "KEY_PATH", self.root / "security.key"),
                        patch.object(alias_memory, "STATE_DIR", self.root),
                        patch("scripts.backup_data.DB_PATH", self.root / "security.sqlite3"),
                        patch("scripts.backup_data.KEY_PATH", self.root / "security.key"),
                        patch("scripts.backup_data.STATE_DIR", self.root)]
        for item in self.patches:
            item.start()
        self.alice = security.create_user("alice", "strong-password-alice")
        self.bob = security.create_user("bob", "strong-password-bob--")

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_login_session_csrf_logout_and_rate_limit(self):
        with self.assertRaisesRegex(ValueError, "账号或密码错误"):
            security.login("alice", "wrong-password")
        token, csrf, user = security.login("alice", "strong-password-alice")
        self.assertEqual(user, self.alice)
        identity = security.session(token)
        self.assertTrue(security.valid_csrf(identity, csrf))
        self.assertFalse(security.valid_csrf(identity, "wrong"))
        new_csrf = security.issue_csrf(token)
        self.assertFalse(security.valid_csrf(security.session(token), csrf))
        self.assertTrue(security.valid_csrf(security.session(token), new_csrf))
        security.logout(token)
        self.assertIsNone(security.session(token))
        for _ in range(4):
            with self.assertRaises(ValueError):
                security.login("alice", "wrong-password")
        with self.assertRaisesRegex(ValueError, "次数过多"):
            security.login("alice", "strong-password-alice")

    def test_encrypted_ai_key_and_isolation(self):
        secret = "test-only-fake-key"
        settings = {"base_url": "https://api.example.com", "model": "fake-model", "api_key": secret}
        security.save_ai_settings(self.alice, settings)
        self.assertEqual(security.load_ai_settings(self.alice), settings)
        self.assertIsNone(security.load_ai_settings(self.bob))
        self.assertNotIn(secret.encode(), security.DB_PATH.read_bytes())
        token = security.CURRENT_USER.set(self.bob)
        try:
            self.assertIsNone(provider_settings.get_settings())
        finally:
            security.CURRENT_USER.reset(token)

    def test_memory_and_job_isolation(self):
        context = security.CURRENT_USER.set(self.alice)
        try:
            alias_memory.add_format_rule("20DV")
            with patch("app.graph.extract", return_value={"fields": {key: {"value": ""} for key in __import__('app.state', fromlist=['FIELDS']).FIELDS}}):
                job_id = start_job([{"name": "fake.pdf", "role": "入货通知", "data": b"demo"}], "rules")
            self.assertEqual(alias_memory.apply_format_rules("1X20DV"), "1X20GP")
        finally:
            security.CURRENT_USER.reset(context)
        context = security.CURRENT_USER.set(self.bob)
        try:
            self.assertEqual(alias_memory.apply_format_rules("1X20DV"), "1X20DV")
            with self.assertRaises(ValueError):
                get_job(job_id)
        finally:
            security.CURRENT_USER.reset(context)

    def test_backup_is_integral_and_has_key(self):
        security.save_ai_settings(self.alice, {"base_url": "https://example.com", "model": "fake", "api_key": "fake"})
        folder = backup(self.root / "backups")
        self.assertTrue((folder / "security.key").exists())
        with closing(sqlite3.connect(folder / "security.sqlite3")) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)

    def test_rejects_spoofed_pdf(self):
        import base64
        with self.assertRaisesRegex(ValueError, "PDF 文件内容"):
            decode_extraction_request({"documents": [{"name": "fake.pdf", "role": "入货通知", "data": base64.b64encode(b"not a pdf").decode()}]})

    def test_first_run_setup_is_one_time(self):
        with security.connection() as db:
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM users")
        class QuietHandler(Handler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = build_opener(ProxyHandler({}))
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with opener.open(base + "/api/session") as response:
                self.assertTrue(json.load(response)["setup_required"])
            body = json.dumps({"username": "first", "password": "first-safe-password"}).encode()
            with opener.open(Request(base + "/api/setup", data=body, headers={"Content-Type": "application/json"})) as response:
                self.assertTrue(json.load(response)["ok"])
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as error:
                opener.open(Request(base + "/api/setup", data=body, headers={"Content-Type": "application/json"}))
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
