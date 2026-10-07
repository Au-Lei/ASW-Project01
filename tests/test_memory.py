"""Human-approved memory must be reversible and contain no shipment values."""

import json
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

from app.nodes.normalize import normalize_fields
from app.services.export import export_review
from app.state import PROJECT_ROOT
from app.tools import alias_memory
from app.web import Handler
from app import security


class MemoryTests(unittest.TestCase):
    def test_http_memory_list_add_and_revoke(self):
        temporary_root = PROJECT_ROOT / ".runtime_tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            memory = Path(folder) / "memory.json"
            defaults = Path(folder) / "defaults.json"
            defaults.write_text("{}", encoding="utf-8")
            class QuietHandler(Handler):
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = build_opener(ProxyHandler({}))
            root = f"http://127.0.0.1:{server.server_port}"
            base = root + "/api/memory"
            try:
                with patch.object(alias_memory, "DEFAULT_FILE", defaults), patch.object(alias_memory, "STATE_DIR", Path(folder)), patch.object(security, "DB_PATH", Path(folder) / "security.sqlite3"):
                    security.create_user("memorytester", "memory-test-password")
                    body = json.dumps({"username": "memorytester", "password": "memory-test-password"}).encode()
                    with opener.open(Request(root + "/api/login", data=body, headers={"Content-Type": "application/json"}), timeout=5) as response:
                        login_data = json.load(response)
                        cookie = response.headers["Set-Cookie"].split(";", 1)[0]
                    def request(payload=None):
                        body = json.dumps(payload).encode("utf-8") if payload else None
                        with opener.open(Request(base, data=body, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": login_data["csrf"]}), timeout=5) as response:
                            return json.load(response)
                    self.assertEqual(request()["formats"], [])
                    self.assertEqual(request({"action": "add_format", "source": "20DV"})["formats"],
                                     [{"source": "20DV", "target": "20GP"}])
                    self.assertEqual(request({"action": "remove_format", "source": "20DV"})["formats"], [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_opt_in_save_view_undo_and_no_business_values(self):
        temporary_root = PROJECT_ROOT / ".runtime_tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            defaults = Path(folder) / "defaults.json"
            memory = Path(folder) / "memory.json"
            defaults.write_text('{"bl_number":["D/R No."]}', encoding="utf-8")
            with patch.object(alias_memory, "DEFAULT_FILE", defaults), patch.object(alias_memory, "MEMORY_FILE", memory):
                label = {"field": "bl_number", "source_label": "Document Receipt No."}
                values = {"bl_number": "TEST123456", "destination": "KOBE"}
                export_review({"values": values, "confirmed_aliases": [label]})
                self.assertFalse(memory.exists(), "unticked labels must not be stored")
                export_review({"values": values, "confirmed_aliases": [
                    {"field": "destination", "source_label": "KOBE", "confirmed": True}]})
                self.assertFalse(memory.exists(), "shipment value must not become a label")

                export_review({"values": values, "confirmed_aliases": [{**label, "confirmed": True}]})
                self.assertIn("Document Receipt No.", alias_memory.list_memory()["aliases"]["bl_number"])
                stored = memory.read_text(encoding="utf-8")
                self.assertNotIn("TEST123456", stored)
                self.assertNotIn("KOBE", stored)

                self.assertTrue(alias_memory.remove_alias("bl_number", "Document Receipt No."))
                self.assertNotIn("Document Receipt No.", alias_memory.load_aliases()["bl_number"])
                self.assertTrue(alias_memory.remove_alias("bl_number", "D/R No."))
                self.assertEqual(alias_memory.load_aliases()["bl_number"], [])
                self.assertEqual(alias_memory.remember_aliases([label]), 1)
                self.assertIn("Document Receipt No.", alias_memory.load_aliases()["bl_number"])

    def test_only_curated_format_rules_affect_normalization(self):
        temporary_root = PROJECT_ROOT / ".runtime_tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            memory = Path(folder) / "memory.json"
            with patch.object(alias_memory, "MEMORY_FILE", memory):
                fields = {"containers": {"value": "1X40HC"}}
                self.assertEqual(normalize_fields(fields)["containers"]["value"], "1X40HC")
                self.assertTrue(alias_memory.add_format_rule("40HC"))
                self.assertEqual(normalize_fields(fields)["containers"]["value"], "1X40HQ")
                self.assertEqual(json.loads(memory.read_text(encoding="utf-8"))["formats"], ["40HC"])
                with self.assertRaisesRegex(ValueError, "审核过"):
                    alias_memory.add_format_rule("CUSTOMER123")
                self.assertTrue(alias_memory.remove_format_rule("40HC"))
                self.assertEqual(normalize_fields(fields)["containers"]["value"], "1X40HC")


if __name__ == "__main__":
    unittest.main()
