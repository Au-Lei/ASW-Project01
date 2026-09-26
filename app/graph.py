"""Orchestrate extraction from one or two booking documents."""

from app.nodes.rule_extract import rule_extract
from app.nodes.normalize import normalize_origin
from app.state import FIELDS
from app.tools.ai_extract import ai_extract
from app.tools.document_reader import read_document
from app.tools.provider_settings import get_settings, request_style


def extract(documents: list[dict], mode: str, on_progress=None) -> dict:
    if not 1 <= len(documents) <= 2:
        raise ValueError("请上传一份或两份单据")
    progress = on_progress or (lambda stage, detail: None)
    for index, document in enumerate(documents, 1):
        progress("read", f"正在读取第 {index}/{len(documents)} 份：{document['name']}")
        try:
            document["text"] = read_document(document["name"], document["data"])
        except (OSError, ValueError) as error:
            if mode != "ai":
                raise
            document["text"] = ""
            settings = get_settings()
            if settings and request_style(settings["base_url"]) == "responses":
                document["read_warning"] = f"{document['name']} 的本地文字读取失败，AI 将尝试直接读取原文件：{error}"
            else:
                document["read_warning"] = f"{document['name']} 的本地文字读取失败，当前厂商仅能处理可读取的文字：{error}"
    if mode == "ai":
        progress("prepare", "正在整理单据文字与版面信息")
        fields, warnings = ai_extract(documents, on_progress=progress)
        warnings = [document["read_warning"] for document in documents if document.get("read_warning")] + warnings
    else:
        warnings = []
        progress("prepare", "正在准备字段匹配规则")
        progress("extract", "正在匹配订舱字段")
        extracted = [(document, rule_extract(document["text"])) for document in documents]
        extracted.sort(key=lambda item: item[0]["role"] == "入货通知", reverse=True)
        fields = {}
        for key in FIELDS:
            candidates = [(document, values[key]) for document, values in extracted if values[key]["value"]]
            if candidates:
                document, choice = candidates[0]
                conflict = len(candidates) == 2 and candidates[0][1]["value"].casefold() != candidates[1][1]["value"].casefold()
                fields[key] = {**choice, "source": document["name"], "conflict": bool(conflict)}
            else:
                fields[key] = {"value": "", "evidence": "", "source": "", "conflict": False}
    progress("normalize", "正在核对字段来源并规范起运港")
    fields["origin"]["value"] = normalize_origin(fields["origin"].get("value", ""))
    return {"fields": fields, "mode": mode, "warnings": warnings, "documents": [{"name": document["name"], "characters": len(document["text"])} for document in documents]}
