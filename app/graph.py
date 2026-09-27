"""Orchestrate extraction from one or two booking documents."""

import re

from app.nodes.rule_extract import rule_extract
from app.nodes.normalize import normalize_origin
from app.state import FIELDS
from app.tools.ai_extract import ai_extract
from app.tools.document_reader import read_document
from app.tools.provider_settings import get_settings, request_style


def comparable_value(key: str, value: str) -> str:
    """Ignore harmless port spelling differences when reporting conflicts."""
    if key == "origin":
        value = normalize_origin(value)
    elif key == "destination":
        value = re.sub(r",\s*(?:SOUTH\s+)?(?:KOREA|CHINA|TURKEY)\s*$", "", value, flags=re.I)
    elif key == "containers":
        compact = re.sub(r"\s+", "", value.upper()).replace("*", "X").replace("×", "X")
        container = re.fullmatch(r"(\d+)X(20|40)(GP|DV|HQ|HC|NOR|REEF|RH)", compact)
        if container:
            box_type = {"DV": "GP", "HC": "HQ"}.get(container.group(3), container.group(3))
            return f"{int(container.group(1))}X{container.group(2)}{box_type}"
    return re.sub(r"\s+", " ", value).strip().casefold()


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
            if key == "bl_number":
                candidates.sort(key=lambda item: item[1].get("identifier_kind") == "bill", reverse=True)
            if candidates:
                document, choice = candidates[0]
                conflict = len(candidates) == 2 and comparable_value(key, candidates[0][1]["value"]) != comparable_value(key, candidates[1][1]["value"])
                if key == "bl_number" and conflict:
                    conflict = candidates[0][1].get("identifier_kind") == candidates[1][1].get("identifier_kind")
                fields[key] = {**choice, "source": document["name"], "conflict": bool(conflict)}
            else:
                fields[key] = {"value": "", "evidence": "", "source": "", "conflict": False}
    progress("normalize", "正在核对字段来源并规范起运港")
    fields["origin"]["value"] = normalize_origin(fields["origin"].get("value", ""))
    return {"fields": fields, "mode": mode, "warnings": warnings, "documents": [{"name": document["name"], "characters": len(document["text"])} for document in documents]}
