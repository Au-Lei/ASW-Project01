"""Create/delete an exact temporary QA account; never use for customer accounts."""

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, "/opt/asw/current" if Path("/opt/asw/current").exists() else str(Path(__file__).resolve().parents[1]))
from app.security import connection, create_user


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "create":
        username = "asw_qa_" + secrets.token_hex(4)
        password = secrets.token_urlsafe(24)
        create_user(username, password)
        print(json.dumps({"username": username, "password": password}))
    elif len(sys.argv) == 3 and sys.argv[1] == "delete" and sys.argv[2].startswith("asw_qa_"):
        with connection() as db:
            row = db.execute("SELECT id FROM users WHERE username=?", (sys.argv[2],)).fetchone()
            if not row:
                raise SystemExit("临时账号不存在")
            user_id = row[0]
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM ai_settings WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM audit WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM users WHERE id=?", (user_id,))
        print("临时账号已删除")
    else:
        raise SystemExit("仅支持 create 或 delete asw_qa_账号")


if __name__ == "__main__":
    main()
