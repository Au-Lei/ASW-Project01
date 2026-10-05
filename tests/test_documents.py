"""Focused documents regression tests, preserved from the original workflow suite."""

import unittest
from unittest.mock import patch
from pathlib import Path
from subprocess import CompletedProcess
from app.tools.document_reader import decode_office_output, read_document
from app.state import PROJECT_ROOT


class DocumentsTests(unittest.TestCase):
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

    def test_legacy_office_output_decodes_utf8_and_windows_code_page(self):
        sample = "场站: 青岛世腾克运"
        self.assertEqual(decode_office_output(sample.encode("utf-8")), sample)
        self.assertEqual(decode_office_output(sample.encode("cp936")), sample)
