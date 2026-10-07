"""Validate transport input before it reaches the extraction workflow."""

import base64
import io
import zipfile
from pathlib import Path

from app.business import DOCUMENT_ROLES, EXTRACTION_MODES, SUPPORTED_SUFFIXES
from app.state import MAX_DOCUMENT_BYTES


def decode_extraction_request(payload: dict) -> tuple[list[dict], str]:
    raw_docs = payload.get("documents", [])
    if not isinstance(raw_docs, list) or not 1 <= len(raw_docs) <= 2:
        raise ValueError("请至少上传一份单据，最多两份")
    mode = payload.get("mode", "rules")
    if not isinstance(mode, str) or mode not in EXTRACTION_MODES:
        raise ValueError("无效的提取模式")
    docs = []
    for raw in raw_docs:
        if not isinstance(raw, dict) or not isinstance(raw.get("role"), str) or raw["role"] not in DOCUMENT_ROLES:
            raise ValueError("文件类型无效")
        name = raw.get("name")
        encoded = raw.get("data")
        if not isinstance(name, str) or not isinstance(encoded, str):
            raise ValueError("文件名称或内容格式无效")
        name = Path(name).name
        if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("支持 PDF、DOCX、XLSX、DOC、RTF、XLS")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, UnicodeError) as error:
            raise ValueError("文件内容编码无效") from error
        if not data or len(data) > MAX_DOCUMENT_BYTES:
            raise ValueError("每份文件须小于 12 MB")
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf" and not data.startswith(b"%PDF-"):
            raise ValueError("PDF 文件内容与扩展名不符")
        if suffix in {".docx", ".xlsx"}:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    files = archive.infolist()
                    if len(files) > 2000 or sum(item.file_size for item in files) > 100 * 1024 * 1024:
                        raise ValueError("Office 文件解压后过大")
                    marker = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
                    if marker not in archive.namelist():
                        raise ValueError("Office 文件内容与扩展名不符")
            except zipfile.BadZipFile as error:
                raise ValueError("Office 文件内容无效") from error
        if suffix in {".doc", ".xls"} and not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ValueError("旧版 Office 文件内容与扩展名不符")
        if suffix == ".rtf" and not data.lstrip().startswith(b"{\\rtf"):
            raise ValueError("RTF 文件内容与扩展名不符")
        docs.append({"name": name, "role": raw["role"], "data": data})
    if len({doc["role"] for doc in docs}) != len(docs):
        raise ValueError("同一类型的文件只能上传一份")
    return docs, mode
