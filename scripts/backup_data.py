"""Consistent local security-data backup; keep archive outside the Git checkout."""

import argparse
from contextlib import closing
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.security import DB_PATH, KEY_PATH
from app.state import STATE_DIR


def backup(destination: Path) -> Path:
    if not DB_PATH.exists():
        raise ValueError("数据库尚不存在")
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    folder = destination / ("asw-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    folder.mkdir(exist_ok=False)
    with closing(sqlite3.connect(DB_PATH)) as source, closing(sqlite3.connect(folder / "security.sqlite3")) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("备份数据库完整性校验失败")
    if KEY_PATH.exists():
        shutil.copy2(KEY_PATH, folder / "security.key")
    users = STATE_DIR / "users"
    if users.exists():
        shutil.copytree(users, folder / "users")
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path, help="受保护的备份目录（推荐外部磁盘）")
    args = parser.parse_args()
    print(backup(args.destination))
