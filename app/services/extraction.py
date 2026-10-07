"""Read, extract, merge, and normalize without HTTP concerns."""

from app.business import EXTRACTION_MODES
from app.models import Document, ExtractionResult, ProgressCallback
from app.nodes.normalize import normalize_fields
from app.nodes.rule_extract import rule_candidates
from app.services.merge import merge_candidates
from app.tools.provider_settings import get_settings, request_style
from app.tools.text_quality import assess_text_quality


def run_pipeline(documents: list[dict], mode: str, *, reader, rule_engine, ai_engine,
                 on_progress: ProgressCallback | None = None) -> dict:
    if not 1 <= len(documents) <= 2:
        raise ValueError("请上传一份或两份单据")
    if mode not in EXTRACTION_MODES:
        raise ValueError("无效的提取模式")
    documents = [Document(name=d["name"], role=d["role"], data=d["data"]).to_dict() for d in documents]
    progress = on_progress or (lambda stage, detail: None)
    for index, document in enumerate(documents, 1):
        progress("read", f"正在读取第 {index}/{len(documents)} 份：{document['name']}")
        try:
            document["text"] = reader(document["name"], document["data"])
        except (OSError, ValueError) as error:
            if mode != "ai":
                raise
            document["text"] = ""
            settings = get_settings()
            if settings and request_style(settings["base_url"]) == "responses":
                document["read_warning"] = f"{document['name']} 的本地文字读取失败，AI 将尝试直接读取原文件：{error}"
            else:
                document["read_warning"] = f"{document['name']} 的本地文字读取失败，当前厂商仅能处理可读取的文字：{error}"
        document["text_quality"], quality_warning = assess_text_quality(document["name"], document["text"])
        document["quality_warning"] = quality_warning
    if mode == "ai":
        progress("prepare", "正在整理单据文字与版面信息")
        fields, warnings = ai_engine(documents, on_progress=progress)
        warnings = [warning for document in documents for warning in (document.get("read_warning"),
                    (f"{document['name']} 几乎没有可读取文字；AI 已尝试读取页面图像，请按原件核对"
                     if document.get("text_quality") == "little_text" and document["name"].lower().endswith(".pdf")
                     else document.get("quality_warning"))) if warning] + warnings
    else:
        warnings = [document["quality_warning"] for document in documents if document.get("quality_warning")]
        progress("prepare", "正在准备字段匹配规则")
        progress("extract", "正在匹配订舱字段")
        extracted = []
        for document in documents:
            values = rule_engine(document["text"])
            if getattr(rule_engine, "__name__", "") == "rule_extract":
                document["rule_candidates"] = rule_candidates(document["text"], values)
            extracted.append((document, values))
        fields = merge_candidates(extracted)
    progress("normalize", "正在核对字段来源并规范业务格式")
    fields = normalize_fields(fields)
    return ExtractionResult(fields=fields, mode=mode, warnings=warnings,
                            documents=[{"name": d["name"], "characters": len(d["text"]), "text_quality": d["text_quality"]}
                                       for d in documents]).to_dict()
