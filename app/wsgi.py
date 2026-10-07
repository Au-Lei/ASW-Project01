"""WSGI HTTP application for local use and HTTPS reverse-proxy deployment."""

import io
import json
import os
from pathlib import Path

from flask import Flask, Response, abort, g, jsonify, make_response, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from app.business import review_config
from app.diagnostics import record_error
from app.graph import extract
from app.jobs import get_job, get_stats, start_job
from app.security import CURRENT_USER, _cipher, audit, create_user, has_users, issue_csrf, login, logout, session, valid_csrf
from app.services.export import export_review
from app.services.requests import decode_extraction_request
from app.state import MAX_DOCUMENT_BYTES, PROJECT_ROOT, TEMPLATE
from app.tools.alias_memory import add_format_rule, list_memory, remove_alias, remove_format_rule
from app.tools.provider_settings import clear_settings, public_settings, test_and_save


app = Flask(__name__, static_folder=None)
# The WSGI server binds only to loopback; Nginx is the sole trusted proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=0)
app.config["MAX_CONTENT_LENGTH"] = 2 * MAX_DOCUMENT_BYTES * 2


@app.before_request
def access_control():
    if not request.path.startswith("/api/"):
        return None
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="请求来源无效", error_code="invalid_origin"), 403
        limit = 2 * MAX_DOCUMENT_BYTES * 2 if request.path in {"/api/extract", "/api/extract/start"} else 128 * 1024
        if request.content_length is None or request.content_length <= 0 or request.content_length > limit:
            return jsonify(error="请求过大或没有内容", error_code="invalid_request"), 400
        if request.mimetype != "application/json":
            return jsonify(error="仅接受 JSON 请求", error_code="invalid_request"), 400
    if request.path in {"/api/session", "/api/login", "/api/setup"}:
        return None
    identity = session(request.cookies.get("asw_session", ""))
    if not identity:
        return jsonify(error="请先登录", error_code="unauthorized"), 401
    if request.method == "POST" and not valid_csrf(identity, request.headers.get("X-CSRF-Token", "")):
        return jsonify(error="安全校验失败，请刷新页面后重试", error_code="csrf_failed"), 403
    g.identity = identity
    g.context_token = CURRENT_USER.set(identity["user_id"])
    return None


@app.teardown_request
def clear_user_context(error):
    token = getattr(g, "context_token", None)
    if token is not None:
        CURRENT_USER.reset(token)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
    response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.errorhandler(ValueError)
def invalid_request(error):
    return jsonify(error=str(error), error_code="invalid_request"), 400


@app.errorhandler(Exception)
def failed_request(error):
    if isinstance(error, HTTPException):
        return jsonify(error="请求不可用", error_code="http_error"), error.code
    record_error("request_failed", error)
    return jsonify(error="处理失败，请联系管理员查看服务日志", error_code="request_failed"), 500


def body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("请求必须是 JSON 对象")
    return payload


@app.get("/")
def index():
    return send_file(PROJECT_ROOT / "app" / "static" / "index.html", mimetype="text/html; charset=utf-8")


@app.get("/static/<name>")
def static_file(name):
    types = {"styles.css": "text/css", "api.js": "text/javascript", "ui.js": "text/javascript",
             "review.js": "text/javascript", "memory.js": "text/javascript", "app.js": "text/javascript",
             "auth.js": "text/javascript"}
    if name not in types:
        abort(404)
    return send_file(PROJECT_ROOT / "app" / "static" / name, mimetype=types[name] + "; charset=utf-8")


@app.get("/api/session")
def session_status():
    token = request.cookies.get("asw_session", "")
    identity = session(token)
    return jsonify(authenticated=bool(identity), username=identity["username"] if identity else None,
                   csrf=issue_csrf(token) if identity else None,
                   setup_required=not has_users() and os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") != "1")


@app.post("/api/setup")
def initial_setup():
    if (os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") == "1" or
            request.remote_addr not in {"127.0.0.1", "::1"} or has_users()):
        return jsonify(error="首次设置仅可在本机且没有账号时使用"), 403
    payload = body()
    username, password = payload.get("username"), payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("账号或密码无效")
    user_id = create_user(username, password, only_first=True)
    audit(user_id, "initial_setup", "ok")
    return jsonify(ok=True)


@app.post("/api/login")
def login_route():
    payload = body()
    username, password = payload.get("username"), payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 40 or len(password) > 256:
        raise ValueError("账号或密码无效")
    token, csrf, _ = login(username, password)
    response = jsonify(authenticated=True, username=username, csrf=csrf)
    response.set_cookie("asw_session", token, httponly=True, secure=request.is_secure,
                        samesite="Strict", max_age=8 * 60 * 60, path="/")
    return response


@app.post("/api/logout")
def logout_route():
    logout(request.cookies.get("asw_session", ""))
    audit(g.identity["user_id"], "logout", "ok")
    response = jsonify(ok=True)
    response.delete_cookie("asw_session", path="/")
    return response


@app.get("/api/review-config")
def get_review_config():
    return jsonify(review_config())


@app.route("/api/config", methods=["GET", "POST"])
def ai_config():
    if request.method == "POST":
        payload = body()
        action = payload.get("action", "save")
        if action == "test":
            test_and_save(str(payload.get("base_url", "")), str(payload.get("api_key", "")), str(payload.get("model", "")))
        elif action == "clear":
            clear_settings()
        else:
            raise ValueError("无效的配置操作")
        audit(g.identity["user_id"], "ai_config", "ok")
    return jsonify({**public_settings(), "template_ready": TEMPLATE.exists()})


@app.route("/api/memory", methods=["GET", "POST"])
def memory():
    if request.method == "POST":
        payload = body()
        action = payload.get("action")
        if action == "remove_alias":
            remove_alias(payload.get("field"), payload.get("source_label"))
        elif action == "add_format":
            add_format_rule(payload.get("source"))
        elif action == "remove_format":
            remove_format_rule(payload.get("source"))
        else:
            raise ValueError("无效的记忆操作")
        audit(g.identity["user_id"], "memory", "ok")
    return jsonify(list_memory())


@app.get("/api/stats")
def stats():
    return jsonify(get_stats())


@app.get("/api/extract/status")
def status():
    try:
        return jsonify(get_job(request.args.get("job_id", "")))
    except ValueError as error:
        return jsonify(error=str(error)), 404


@app.post("/api/extract/start")
@app.post("/api/extract")
def run_extract():
    docs, mode = decode_extraction_request(body())
    audit(g.identity["user_id"], "extract:" + mode, "submitted")
    if request.path.endswith("/start"):
        return jsonify(job_id=start_job(docs, mode)), 202
    return jsonify(extract(docs, mode))


@app.post("/api/export")
def export():
    data, memory_warning = export_review(body())
    audit(g.identity["user_id"], "export", "ok")
    response = send_file(io.BytesIO(data), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name="business_contact_sheet.xlsx")
    if memory_warning:
        response.headers["X-Alias-Memory-Warning"] = "save-failed"
    return response


def serve(port=8765):
    from waitress import serve as waitress_serve
    if os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") == "1" and not has_users():
        raise RuntimeError("服务器模式尚无账号，请先创建管理员账号")
    _cipher()
    waitress_serve(app, host="127.0.0.1", port=port, threads=4,
                   trusted_proxy="127.0.0.1", trusted_proxy_headers="x-forwarded-proto",
                   max_request_body_size=2 * MAX_DOCUMENT_BYTES * 2)
