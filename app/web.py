"""Local HTTP entry point for the review and export UI."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from app.graph import extract
from app.jobs import get_job, get_stats, start_job
from app.state import MAX_DOCUMENT_BYTES, PROJECT_ROOT, TEMPLATE
from app.business import review_config
from app.diagnostics import record_error
from app.services.requests import decode_extraction_request
from app.services.export import export_review
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
        elif route.path == "/api/review-config":
            self.send_json(200, review_config())
        elif route.path.startswith("/static/"):
            filename = route.path.removeprefix("/static/")
            allowed = {"styles.css": "text/css", "api.js": "text/javascript",
                       "ui.js": "text/javascript", "review.js": "text/javascript", "app.js": "text/javascript"}
            if filename not in allowed:
                self.send_error(404)
                return
            data = (PROJECT_ROOT / "app" / "static" / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", allowed[filename] + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
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
            if not isinstance(payload, dict):
                raise ValueError("请求必须是 JSON 对象")
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
                docs, mode = decode_extraction_request(payload)
                if self.path == "/api/extract/start":
                    self.send_json(202, {"job_id": start_job(docs, mode)})
                else:
                    self.send_json(200, extract(docs, mode))
            elif self.path == "/api/export":
                data, memory_warning = export_review(payload)
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
            self.send_json(400, {"error": str(error), "error_code": "invalid_request"})
        except (BrokenPipeError, ConnectionResetError) as error:
            record_error("client_disconnected", error)
        except Exception as error:
            record_error("request_failed", error)
            self.send_json(500, {"error": f"处理失败：{error}", "error_code": "request_failed"})



def serve(port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"业务联系单 MVP 已启动：http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
