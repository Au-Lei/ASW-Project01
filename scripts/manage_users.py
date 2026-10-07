"""Create a local account: python scripts/manage_users.py add USERNAME."""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.security import create_user


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "add":
        raise SystemExit("用法：python scripts/manage_users.py add 用户名")
    password = getpass.getpass("新密码（至少 12 位）：")
    if password != getpass.getpass("再次输入密码："):
        raise SystemExit("两次密码不一致")
    try:
        create_user(sys.argv[2], password)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print("账号已创建")
