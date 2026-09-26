"""Local HTTP entry point for the review and export UI."""

import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.graph import extract
from app.jobs import get_job, get_stats, start_job
from app.state import MAX_DOCUMENT_BYTES, PROJECT_ROOT, TEMPLATE
from app.tools.excel_export import make_workbook
from app.tools.alias_memory import remember_aliases
from app.tools.provider_settings import clear_settings, public_settings, test_and_save


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        if route.path == "/":
            data = (PROJECT_ROOT / "app" / "static" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route.path == "/api/config":
            self.send_json(200, {**public_settings(), "template_ready": TEMPLATE.exists()})
        elif route.path == "/api/stats":
            self.send_json(200, get_stats())
        elif route.path == "/api/extract/status":
            try:
                job_id = parse_qs(route.query).get("job_id", [""])[0]
                self.send_json(200, get_job(job_id))
            except ValueError as error:
                self.send_json(404, {"error": str(error)})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2 * MAX_DOCUMENT_BYTES * 2:
                raise ValueError("请求过大或没有内容")
            payload = json.loads(self.rfile.read(size))
            if self.path == "/api/config":
                action = payload.get("action", "save")
                if action == "test":
                    test_and_save(str(payload.get("base_url", "")), str(payload.get("api_key", "")), str(payload.get("model", "")))
                elif action == "clear":
                    clear_settings()
                else:
                    raise ValueError("无效的配置操作")
                self.send_json(200, {**public_settings(), "template_ready": TEMPLATE.exists()})
            elif self.path in {"/api/extract", "/api/extract/start"}:
                raw_docs = payload.get("documents", [])
                if not isinstance(raw_docs, list) or not 1 <= len(raw_docs) <= 2:
                    raise ValueError("请至少上传一份单据，最多两份")
                docs = []
                for raw in raw_docs:
                    if raw.get("role") not in {"订舱委托书", "入货通知"}:
                        raise ValueError("文件类型无效")
                    data = base64.b64decode(raw["data"], validate=True)
                    if not data or len(data) > MAX_DOCUMENT_BYTES:
                        raise ValueError("每份文件须小于 12 MB")
                    docs.append({"name": Path(raw["name"]).name, "role": raw["role"], "data": data})
                if len({document["role"] for document in docs}) != len(docs):
                    raise ValueError("同一类型的文件只能上传一份")
                mode = payload.get("mode", "rules")
                if mode not in {"rules", "ai"}:
                    raise ValueError("无效的提取模式")
                if self.path == "/api/extract/start":
                    self.send_json(202, {"job_id": start_job(docs, mode)})
                else:
                    self.send_json(200, extract(docs, mode))
            elif self.path == "/api/export":
                values = payload.get("values", {})
                data = make_workbook(values)
                raw_aliases = payload.get("confirmed_aliases", [])
                if not isinstance(raw_aliases, list):
                    raise ValueError("字段别名格式无效")
                candidates = [item for item in raw_aliases if isinstance(item, dict) and str(values.get(item.get("field"), "")).strip()]
                memory_warning = False
                try:
                    remember_aliases(candidates)
                except OSError:
                    memory_warning = True
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", 'attachment; filename="business_contact_sheet.xlsx"')
                if memory_warning:
                    self.send_header("X-Alias-Memory-Warning", "save-failed")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
        except Exception as error:
            self.send_json(500, {"error": f"处理失败：{error}"})



def serve(port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"业务联系单 MVP 已启动：http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
