"""Validated, process-local AI connection for the single-user demo."""

import json
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, getproxies, urlopen


_lock = Lock()
_settings: dict | None = None


def normalize_base_url(raw: str) -> str:
    base_url = raw.strip().rstrip("/")
    parts = urlsplit(base_url)
    if not base_url or len(base_url) > 500 or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("请输入有效的 base_url，例如 https://api.openai.com/v1")
    if parts.scheme not in {"http", "https"}:
        raise ValueError("base_url 仅支持 http 或 https")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("远程 AI 服务必须使用 HTTPS；HTTP 仅允许本机地址")
    if base_url.endswith(("/responses", "/chat/completions")):
        raise ValueError("base_url 请填接口根地址，不要包含 /responses 或 /chat/completions")
    return base_url


def request_style(base_url: str) -> str:
    """Official OpenAI endpoint supports PDF input; other compatible APIs use text chat."""
    return "responses" if urlsplit(base_url).hostname == "api.openai.com" else "chat"


def endpoint(base_url: str) -> str:
    return base_url + ("/responses" if request_style(base_url) == "responses" else "/chat/completions")


def validate_fields(base_url: str, api_key: str, model: str) -> dict:
    base_url = normalize_base_url(base_url)
    api_key = api_key.strip()
    model = model.strip()
    if not api_key or len(api_key) > 4096 or any(char.isspace() for char in api_key):
        raise ValueError("请输入有效的 API Key")
    if not model or len(model) > 100 or any(char.isspace() for char in model):
        raise ValueError("请输入有效的模型名称")
    return {"base_url": base_url, "api_key": api_key, "model": model}


def call_service(settings: dict, payload: dict, *, timeout: int = 120) -> dict:
    request = Request(
        endpoint(settings["base_url"]),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + settings["api_key"], "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:350].replace(settings["api_key"], "[REDACTED]")
        raise ValueError(f"AI 服务返回 HTTP {error.code}：{detail}") from error
    except (URLError, TimeoutError, OSError) as error:
        reason = str(error).replace(settings["api_key"], "[REDACTED]")
        proxy = getproxies().get(urlsplit(settings["base_url"]).scheme)
        if proxy and ("10061" in reason or "refused" in reason.lower()):
            proxy_parts = urlsplit(proxy)
            proxy_address = proxy_parts.hostname or "未知代理"
            if proxy_parts.port:
                proxy_address += f":{proxy_parts.port}"
            raise ValueError(f"连接被拒绝：当前程序使用的代理 {proxy_address} 可能未启动。请修复代理或从正常网络环境启动程序；base_url 和模型暂未经过验证") from error
        raise ValueError(f"无法连接 AI 服务（{reason}）。请检查 base_url、网络或代理设置") from error


def test_and_save(base_url: str, api_key: str, model: str) -> dict:
    settings = validate_fields(base_url, api_key, model)
    if request_style(settings["base_url"]) == "responses":
        payload = {
            "model": settings["model"], "input": "请输出 ok 为 true 的 JSON 对象。", "store": False,
            "text": {"format": {"type": "json_schema", "name": "connection_test", "strict": True,
                                "schema": {"type": "object", "additionalProperties": False,
                                           "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}},
        }
    else:
        payload = {"model": settings["model"], "messages": [{"role": "user", "content": "只输出 JSON 对象：{\"ok\":true}"}],
                   "response_format": {"type": "json_object"}}
    result = call_service(settings, payload, timeout=20)
    if request_style(settings["base_url"]) == "responses":
        answer = "".join(part.get("text", "") for item in result.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text")
    else:
        choices = result.get("choices", [])
        answer = choices[0].get("message", {}).get("content", "") if choices else ""
    try:
        parsed = json.loads(answer)
    except (TypeError, ValueError) as error:
        raise ValueError("AI 服务已连接，但模型没有返回可解析的 JSON；请检查模型是否支持结构化输出") from error
    if not isinstance(parsed, dict) or parsed.get("ok") is not True:
        raise ValueError("AI 服务已连接，但模型未通过 JSON 提取测试")
    global _settings
    with _lock:
        _settings = settings
    return public_settings()


def get_settings() -> dict | None:
    with _lock:
        return _settings.copy() if _settings else None


def public_settings() -> dict:
    current = get_settings()
    return {
        "ai_available": bool(current),
        "base_url": current["base_url"] if current else None,
        "model": current["model"] if current else None,
        "request_style": request_style(current["base_url"]) if current else None,
        "storage": "memory",
    }


def clear_settings() -> None:
    global _settings
    with _lock:
        _settings = None
