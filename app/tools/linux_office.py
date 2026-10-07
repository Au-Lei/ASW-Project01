"""Isolated LibreOffice conversion for legacy documents on Linux."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.state import RUNTIME_TMP_DIR


def to_pdf(name: str, data: bytes) -> bytes:
    suffix = Path(name).suffix.lower()
    if suffix not in {".doc", ".docx", ".rtf", ".xls"}:
        raise ValueError("不支持该格式的版面转换")
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise RuntimeError("服务器缺少 LibreOffice，无法读取旧版 Office 单据")
    root = RUNTIME_TMP_DIR
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix="office-") as folder:
        work = Path(folder)
        source = work / ("source" + suffix)
        source.write_bytes(data)
        profile = (work / "profile").as_uri()
        command = [executable, "-env:UserInstallation=" + profile, "--headless", "--convert-to", "pdf", "--outdir", str(work), str(source)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=60, check=False,
                                    env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"})
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("LibreOffice 转换超时") from error
        output = work / "source.pdf"
        if result.returncode or not output.exists():
            raise RuntimeError("LibreOffice 转换失败，请检查文件是否损坏")
        if output.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("转换后的 PDF 超过 20 MB")
        return output.read_bytes()
