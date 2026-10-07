"""Linux converter contract without requiring LibreOffice on Windows CI."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.tools import linux_office


class LinuxOfficeTests(unittest.TestCase):
    def test_missing_binary_is_actionable(self):
        with patch.object(linux_office.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "缺少 LibreOffice"):
                linux_office.to_pdf("booking.doc", b"test")

    def test_isolated_conversion_uses_pdf_and_closes_temp_files(self):
        def fake_run(command, **kwargs):
            self.assertIn("--headless", command)
            self.assertTrue(any(part.startswith("-env:UserInstallation=") for part in command))
            output_dir = Path(command[command.index("--outdir") + 1])
            (output_dir / "source.pdf").write_bytes(b"%PDF-1.4\nsynthetic")
            return SimpleNamespace(returncode=0)

        with patch.object(linux_office.shutil, "which", return_value="/usr/bin/soffice"), \
             patch.object(linux_office.subprocess, "run", side_effect=fake_run):
            self.assertTrue(linux_office.to_pdf("booking.doc", b"synthetic").startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
