"""One-time synthetic HTTPS acceptance test; cleans up its temporary account."""

import base64
import io
import json
import os
import secrets
import sys
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from openpyxl import load_workbook

sys.path.insert(0, "/opt/asw/current" if Path("/opt/asw/current").exists() else str(Path(__file__).resolve().parents[1]))
from app.security import connection, create_user


BASE = "https://47.122.105.169"
ORIGIN = BASE


def main():
    username = os.environ.get("ASW_QA_USERNAME") or "asw_qa_" + secrets.token_hex(4)
    password = os.environ.get("ASW_QA_PASSWORD") or secrets.token_urlsafe(24)
    externally_managed = bool(os.environ.get("ASW_QA_USERNAME") and os.environ.get("ASW_QA_PASSWORD"))
    user_id = None if externally_managed else create_user(username, password)
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def post(path, payload, csrf=None):
        headers = {"Content-Type": "application/json", "Origin": ORIGIN}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = Request(BASE + path, json.dumps(payload).encode(), headers)
        with client.open(request, timeout=90) as response:
            return response.read()

    try:
        login = json.loads(post("/api/login", {"username": username, "password": password}))
        csrf = login["csrf"]
        rtf = b"{\\rtf1\\ansi Bill of Lading: QATEST123456\\par Vessel/Voyage: TEST VESSEL / 123E\\par POL: QINGDAO\\par POD: SINGAPORE\\par 1X20GP}"
        submitted = json.loads(post("/api/extract/start", {"mode": "rules", "documents": [{
            "name": "synthetic.rtf", "role": "入货通知", "data": base64.b64encode(rtf).decode()
        }]}, csrf))
        for _ in range(40):
            with client.open(BASE + "/api/extract/status?job_id=" + submitted["job_id"], timeout=20) as response:
                job = json.load(response)
            if job["status"] != "running":
                break
            time.sleep(1)
        if job["status"] != "completed":
            raise RuntimeError("提取未完成：" + str(job.get("error")))
        values = {key: str(item.get("value", "")) for key, item in job["result"]["fields"].items()}
        values["bl_number"] = "QATEST123456"
        workbook_bytes = post("/api/export", {"values": values}, csrf)
        workbook = load_workbook(io.BytesIO(workbook_bytes), read_only=True)
        try:
            if workbook.active["B8"].value != "QATEST123456":
                raise RuntimeError("导出 Excel 的提单号不正确")
        finally:
            workbook.close()
        print("PASS: HTTPS login, RTF upload/conversion, extraction, review values, Excel export")
    finally:
        if user_id is not None:
            with connection() as db:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                db.execute("DELETE FROM ai_settings WHERE user_id=?", (user_id,))
                db.execute("DELETE FROM audit WHERE user_id=?", (user_id,))
                db.execute("DELETE FROM users WHERE id=?", (user_id,))


if __name__ == "__main__":
    main()
