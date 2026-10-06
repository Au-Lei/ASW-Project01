"""Use document layout, extracted text, and approved aliases for AI extraction."""

import base64
import json
from pathlib import Path
from urllib.parse import urlsplit

from app.nodes.normalize import normalize_fields
from app.state import FIELDS, PROJECT_ROOT
from app.tools.alias_memory import load_aliases
from app.tools.layout_pdf import word_to_pdf
from app.tools.pdf_images import MAX_VISION_PAGES, render_pdf_pages
from app.tools.provider_settings import call_service, get_settings, request_style


def _file_part(filename: str, data: bytes, mime_type: str, *, high_detail: bool = False) -> dict:
    part = {"type": "input_file", "filename": filename, "file_data": f"data:{mime_type};base64," + base64.b64encode(data).decode("ascii")}
    if high_detail:
        part["detail"] = "high"
    return part


def build_request(documents: list[dict], model: str | None = None) -> tuple[dict, list[str]]:
    """Build the API request separately so layout and schema can be tested offline."""
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            key: {
                "type": "object", "additionalProperties": False,
                "properties": {name: {"type": "string"} for name in ("value", "evidence", "source", "source_label", "review_reason")},
                "required": ["value", "evidence", "source", "source_label", "review_reason"],
            }
            for key in FIELDS
        },
        "required": list(FIELDS),
    }
    instructions = (PROJECT_ROOT / "prompts" / "booking_extraction.txt").read_text(encoding="utf-8")
    aliases = {field: labels for field, labels in load_aliases().items() if labels}
    content = [
        {"type": "input_text", "text": instructions},
        {"type": "input_text", "text": "已由业务员确认的字段别名（仅供理解标签，不代替原件证据）：" + json.dumps(aliases, ensure_ascii=False)},
    ]
    warnings = []
    for doc in documents:
        name = doc["name"]
        content.append({"type": "input_text", "text": f"\n### 原始上传文件：{name}（{doc['role']}）\n若下方有同名 PDF，它只是此文件的版面版本，source 仍须填写原始上传文件名 {name}。提取的文字如下；如文字顺序与页面版面冲突，以页面版面为准：\n{doc['text'][:40000]}"})
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf":
            content.append(_file_part(name, doc["data"], "application/pdf", high_detail=True))
        elif suffix in {".doc", ".docx", ".rtf"}:
            try:
                pdf = word_to_pdf(name, doc["data"])
                if len(pdf) > 20 * 1024 * 1024:
                    raise ValueError("转换后的 PDF 超过 20 MB")
                content.append(_file_part(Path(name).stem + ".pdf", pdf, "application/pdf", high_detail=True))
            except (RuntimeError, ValueError, OSError) as error:
                warnings.append(f"{name} 未能转换版面 PDF，改用原文件：{error}")
                mime = {".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".rtf": "application/rtf"}[suffix]
                content.append(_file_part(name, doc["data"], mime))
        elif suffix in {".xls", ".xlsx"}:
            mime = "application/vnd.ms-excel" if suffix == ".xls" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            content.append(_file_part(name, doc["data"], mime))
    payload = {
        "model": model or "gpt-4.1-mini",
        "store": False,
        "input": [{"role": "user", "content": content}],
        "text": {"format": {"type": "json_schema", "name": "booking_fields", "strict": True, "schema": schema}},
    }
    return payload, warnings


def build_chat_request(documents: list[dict], model: str, *, base_url: str = "") -> tuple[dict, list[str]]:
    """Use PDF page images only for the confirmed DeepSeek Flash vision endpoint."""
    instructions = (PROJECT_ROOT / "prompts" / "booking_extraction.txt").read_text(encoding="utf-8")
    aliases = {field: labels for field, labels in load_aliases().items() if labels}
    schema_example = {field: {name: "" for name in ("value", "evidence", "source", "source_label", "review_reason")} for field in FIELDS}
    source_text = "\n\n".join(f"### {doc['name']}（{doc['role']}）\n{doc['text'][:40000]}" for doc in documents)
    prompt = (
        instructions + "\n仅输出 JSON 对象，必须包含以下全部字段和子字段；找不到的值用空字符串，不要猜测。"
        "\nJSON 格式示例：" + json.dumps(schema_example, ensure_ascii=False)
        + "\n已确认的标签别名：" + json.dumps(aliases, ensure_ascii=False)
        + "\n原始单据文字：\n" + source_text
    )
    content: str | list[dict] = prompt
    warnings = []
    supports_vision = urlsplit(base_url).hostname == "api.deepseek.com" and model.lower() == "deepseek-flash"
    if supports_vision:
        parts = [{"type": "text", "text": prompt}]
        for doc in documents:
            if Path(doc["name"]).suffix.lower() != ".pdf":
                continue
            try:
                images, total = render_pdf_pages(doc["data"])
            except (RuntimeError, ValueError, OSError):
                warnings.append(f"{doc['name']} 的 PDF 页面图像未能读取；仅使用可提取的文字，请人工核对")
                continue
            for index, image in enumerate(images, 1):
                parts.append({"type": "text", "text": f"{doc['name']} 第 {index} 页页面图像；请从图像核对标签、表格和字段来源。"})
                parts.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii"), "detail": "high"}})
            if total > MAX_VISION_PAGES:
                warnings.append(f"{doc['name']} 共 {total} 页，AI 只查看前 {MAX_VISION_PAGES} 页图像；后续页面仍需人工核对")
        if len(parts) > 1:
            content = parts
            warnings.append("DeepSeek Flash 已接收 PDF 页面图像；可能产生额外图像费用，请按原件核对结果")
    if not isinstance(content, list):
        warnings.append("当前模型仅发送提取到的文字；扫描件或复杂表格可能识别不全，请人工核对")
    return {"model": model, "messages": [{"role": "user", "content": content}], "response_format": {"type": "json_object"}}, warnings


def ai_extract(documents: list[dict], on_progress=None) -> tuple[dict, list[str]]:
    settings = get_settings()
    if not settings:
        raise ValueError("请先在 AI 提取设置中填写 base_url、API Key、model 并通过连接测试")
    style = request_style(settings["base_url"])
    if style == "responses":
        payload, warnings = build_request(documents, settings["model"])
    else:
        payload, warnings = build_chat_request(documents, settings["model"], base_url=settings["base_url"])
        has_image = any(isinstance(part, dict) and part.get("type") == "image_url"
                        for part in payload["messages"][0]["content"]) if isinstance(payload["messages"][0]["content"], list) else False
        if not any(doc["text"].strip() for doc in documents) and not has_image:
            raise ValueError("单据没有可读取的文字；扫描版 PDF 可选用支持图片的 DeepSeek Flash 或支持 PDF 的 OpenAI 模型")
    if on_progress:
        on_progress("extract", f"正在等待 AI 模型 {settings['model']} 返回结果")
    body = call_service(settings, payload)
    if on_progress:
        on_progress("normalize", "正在解析 AI 返回的字段与来源")
    if style == "responses":
        output = "".join(item.get("text", "") for message in body.get("output", []) for item in message.get("content", []) if item.get("type") == "output_text")
    else:
        choices = body.get("choices", [])
        output = choices[0].get("message", {}).get("content", "") if choices else ""
    if not output:
        raise ValueError("AI 服务未返回字段内容")
    parsed = json.loads(output)
    if not isinstance(parsed, dict) or any(field not in parsed or not isinstance(parsed[field], dict) for field in FIELDS):
        raise ValueError("AI 返回的字段格式不完整，请换用其他模型或重试")
    filenames = {doc["name"] for doc in documents}
    rendered_names = {Path(doc["name"]).stem + ".pdf": doc["name"] for doc in documents if Path(doc["name"]).suffix.lower() in {".doc", ".docx", ".rtf"}}
    fields = {}
    for field in FIELDS:
        raw = parsed[field]
        value = str(raw.get("value", "")).strip()[:160]
        source = str(raw.get("source", "")).strip()
        source = rendered_names.get(source, source)
        reason = str(raw.get("review_reason", "")).strip()[:200]
        if value and source not in filenames:
            reason = (reason + "；" if reason else "") + "来源文件名未匹配，请核对"
            source = documents[0]["name"] if len(documents) == 1 else ""
        fields[field] = {
            "value": value,
            "evidence": str(raw.get("evidence", "")).strip()[:220],
            "source": source if value else "",
            "source_label": str(raw.get("source_label", "")).strip()[:80] if value else "",
            "review_reason": reason,
        }
    return normalize_fields(fields), warnings
