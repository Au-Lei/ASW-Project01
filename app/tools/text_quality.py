"""Detect document-reading failures before field extraction obscures them."""

from pathlib import Path


def assess_text_quality(name: str, text: str) -> tuple[str, str]:
    """Return a coarse quality state and a user-facing warning, without document data."""
    suffix = Path(name).suffix.lower()
    visible = text.strip()
    if len(visible) < 24:
        return "little_text", f"{name} 几乎没有可读取文字；扫描件的规则提取会漏项，可使用 OCR 或支持图像的 AI 并人工核对"
    replacements = visible.count("\ufffd")
    if replacements >= 8 and replacements / len(visible) >= 0.01:
        return "garbled", f"{name} 的部分文字读取为乱码；相关字段可能漏识别，请核对原件或使用 OCR"
    if suffix == ".pdf" and "\ufffd" in visible and replacements >= 3:
        return "garbled", f"{name} 的 PDF 存在乱码字符；请重点核对中文场站等字段"
    return "ok", ""
