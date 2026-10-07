"""Local HTTP entry point for the review and export UI."""

import json
import os
from http.cookies import SimpleCookie
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
from app.tools.alias_memory import add_format_rule, list_memory, remove_alias, remove_format_rule
from app.security import CURRENT_USER, _cipher, audit, create_user, has_users, issue_csrf, login, logout, session, valid_csrf


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """pythonw has no stderr; avoid aborting responses during access logging."""
        return

    def _session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie["asw_session"].value if "asw_session" in cookie else ""
        except Exception:
            token = ""
        return token, session(token)

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")

    def send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        if route.path.startswith("/api/"):
            token, identity = self._session()
            if route.path == "/api/session":
                self.send_json(200, {"authenticated": bool(identity), "username": identity["username"] if identity else None,
                                     "csrf": issue_csrf(token) if identity else None,
                                     "setup_required": not has_users() and os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") != "1"})
                return
            if not identity:
                self.send_json(401, {"error": "请先登录", "error_code": "unauthorized"})
                return
            context_token = CURRENT_USER.set(identity["user_id"])
            try:
                self._authenticated_get(route)
            finally:
                CURRENT_USER.reset(context_token)
            return
        self._public_get(route)

    def _public_get(self, route):
        if route.path == "/":
            data = (PROJECT_ROOT / "app" / "static" / "index.html").read_bytes()
            self.send_response(200)
            self._security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route.path.startswith("/static/"):
            filename = route.path.removeprefix("/static/")
            allowed = {"styles.css": "text/css", "api.js": "text/javascript",
                       "ui.js": "text/javascript", "review.js": "text/javascript",
                       "memory.js": "text/javascript", "app.js": "text/javascript", "auth.js": "text/javascript"}
            if filename not in allowed:
                self.send_error(404)
                return
            data = (PROJECT_ROOT / "app" / "static" / filename).read_bytes()
            self.send_response(200)
            self._security_headers()
            self.send_header("Content-Type", allowed[filename] + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def _authenticated_get(self, route):
        if route.path == "/api/review-config":
            self.send_json(200, review_config())
        elif route.path == "/api/config":
            self.send_json(200, {**public_settings(), "template_ready": TEMPLATE.exists()})
        elif route.path == "/api/memory":
            self.send_json(200, list_memory())
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
        token, identity = self._session()
        if self.path not in {"/api/login", "/api/setup"}:
            if not identity:
                self.send_json(401, {"error": "请先登录", "error_code": "unauthorized"})
                return
            if not valid_csrf(identity, self.headers.get("X-CSRF-Token", "")):
                self.send_json(403, {"error": "安全校验失败，请刷新页面后重试", "error_code": "csrf_failed"})
                return
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}" and origin != f"https://{self.headers.get('Host')}":
            self.send_json(403, {"error": "请求来源无效"})
            return
        context_token = CURRENT_USER.set(identity["user_id"] if identity else None)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            limit = 2 * MAX_DOCUMENT_BYTES * 2 if self.path in {"/api/extract", "/api/extract/start"} else 128 * 1024
            if size <= 0 or size > limit:
                raise ValueError("请求过大或没有内容")
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise ValueError("仅接受 JSON 请求")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("请求必须是 JSON 对象")
            if self.path == "/api/setup":
                if os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") == "1" or self.client_address[0] not in {"127.0.0.1", "::1"} or has_users():
                    self.send_json(403, {"error": "首次设置仅可在本机且没有账号时使用"})
                    return
                username, password = payload.get("username"), payload.get("password")
                if not isinstance(username, str) or not isinstance(password, str):
                    raise ValueError("账号或密码无效")
                user_id = create_user(username, password, only_first=True)
                audit(user_id, "initial_setup", "ok")
                self.send_json(200, {"ok": True})
            elif self.path == "/api/login":
                username, password = payload.get("username"), payload.get("password")
                if not isinstance(username, str) or not isinstance(password, str) or len(username) > 40 or len(password) > 256:
                    raise ValueError("账号或密码无效")
                login_token, csrf, user_id = login(username, password)
                data = json.dumps({"authenticated": True, "username": username, "csrf": csrf}).encode()
                self.send_response(200)
                self._security_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" and self.client_address[0] in {"127.0.0.1", "::1"} else ""
                self.send_header("Set-Cookie", f"asw_session={login_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/api/logout":
                logout(token)
                audit(identity["user_id"], "logout", "ok")
                self.send_response(200)
                self._security_headers()
                self.send_header("Set-Cookie", "asw_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif self.path == "/api/config":
                action = payload.get("action", "save")
                if action == "test":
                    test_and_save(str(payload.get("base_url", "")), str(payload.get("api_key", "")), str(payload.get("model", "")))
                elif action == "clear":
                    clear_settings()
                else:
                    raise ValueError("无效的配置操作")
                self.send_json(200, {**public_settings(), "template_ready": TEMPLATE.exists()})
                audit(identity["user_id"], "ai_config", "ok")
            elif self.path in {"/api/extract", "/api/extract/start"}:
                docs, mode = decode_extraction_request(payload)
                if self.path == "/api/extract/start":
                    self.send_json(202, {"job_id": start_job(docs, mode)})
                else:
                    self.send_json(200, extract(docs, mode))
                audit(identity["user_id"], "extract:" + mode, "submitted")
            elif self.path == "/api/memory":
                action = payload.get("action")
                if action == "remove_alias":
                    remove_alias(payload.get("field"), payload.get("source_label"))
                elif action == "add_format":
                    add_format_rule(payload.get("source"))
                elif action == "remove_format":
                    remove_format_rule(payload.get("source"))
                else:
                    raise ValueError("无效的记忆操作")
                self.send_json(200, list_memory())
                audit(identity["user_id"], "memory", "ok")
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
                audit(identity["user_id"], "export", "ok")
            else:
                self.send_error(404)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error), "error_code": "invalid_request"})
        except (BrokenPipeError, ConnectionResetError) as error:
            record_error("client_disconnected", error)
        except Exception as error:
            record_error("request_failed", error)
            self.send_json(500, {"error": "处理失败，请联系管理员查看服务日志", "error_code": "request_failed"})
        finally:
            CURRENT_USER.reset(context_token)



def serve(port: int = 8765) -> None:
    if os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") == "1" and not has_users():
        raise RuntimeError("服务器模式尚无账号，请先运行 python scripts/manage_users.py add <用户名>")
    _cipher()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"业务联系单 MVP 已启动：http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
