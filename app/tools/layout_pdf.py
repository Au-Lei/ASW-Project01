"""Preserve Word table layout for vision-capable document extraction."""

import os
import subprocess
import tempfile
from pathlib import Path

import pdfplumber

from app.state import PROJECT_ROOT


def word_to_pdf(name: str, data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Word 版面转换目前需要 Windows 和 Microsoft Office")
    suffix = Path(name).suffix.lower()
    if suffix not in {".doc", ".docx", ".rtf"}:
        raise ValueError("只支持 Word/RTF 文件版面转换")
    temporary_root = PROJECT_ROOT / ".runtime_tmp"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=temporary_root, suffix=suffix, delete=False) as source_file:
        source_file.write(data)
        source = Path(source_file.name)
    with tempfile.NamedTemporaryFile(dir=temporary_root, suffix=".pdf", delete=False) as pdf_file:
        output = Path(pdf_file.name)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(Path(__file__).with_name("word_to_pdf.ps1")), "-Source", str(source), "-Destination", str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
        )
        if output.stat().st_size == 0:
            raise RuntimeError("Word 转 PDF 失败：" + result.stderr.strip()[:250])
        data = output.read_bytes()
        try:
            with pdfplumber.open(output) as pdf:
                if not pdf.pages:
                    raise ValueError("PDF 没有页面")
        except Exception as error:
            raise RuntimeError("Word 转换出的 PDF 无法读取：" + str(error)) from error
        return data
    finally:
        source.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
