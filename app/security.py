"""Local account, session, audit and encrypted settings storage."""

import contextvars
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.state import STATE_DIR


DB_PATH = STATE_DIR / "security.sqlite3"
KEY_PATH = STATE_DIR / "security.key"
CURRENT_USER = contextvars.ContextVar("current_user", default=None)
SESSION_SECONDS = 8 * 60 * 60
IDLE_SECONDS = 30 * 60
_key_lock = threading.Lock()


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            salt BLOB NOT NULL, password_hash BLOB NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
            csrf_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, last_seen INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS ai_settings(user_id INTEGER PRIMARY KEY, base_url TEXT NOT NULL,
            model TEXT NOT NULL, encrypted_key BLOB NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at INTEGER NOT NULL,
            user_id INTEGER, event TEXT NOT NULL, outcome TEXT NOT NULL);
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def _hash_password(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)


def create_user(username: str, password: str, *, only_first: bool = False) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
        raise ValueError("账号须为 3-40 位字母、数字或 _.-")
    if len(password) < 12 or len(password) > 256:
        raise ValueError("密码须为 12-256 位")
    salt = secrets.token_bytes(16)
    with connection() as db:
        if only_first:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise ValueError("管理员账号已创建")
        cursor = db.execute("INSERT INTO users(username,salt,password_hash,created_at) VALUES(?,?,?,?)",
                            (username, salt, _hash_password(password, salt), int(time.time())))
        return cursor.lastrowid


def has_users() -> bool:
    with connection() as db:
        return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def audit(user_id, event: str, outcome: str) -> None:
    with connection() as db:
        db.execute("INSERT INTO audit(at,user_id,event,outcome) VALUES(?,?,?,?)",
                   (int(time.time()), user_id, event, outcome))


def login(username: str, password: str):
    now = int(time.time())
    with connection() as db:
        recent = db.execute("SELECT COUNT(*) FROM audit WHERE event=? AND outcome='failed' AND at>?",
                            ("login:" + username, now - 15 * 60)).fetchone()[0]
        if recent >= 5:
            raise ValueError("登录失败次数过多，请 15 分钟后再试")
        row = db.execute("SELECT id,salt,password_hash FROM users WHERE username=?", (username,)).fetchone()
    salt = row[1] if row else bytes(16)
    matched = hmac.compare_digest(_hash_password(password, salt), row[2] if row else bytes(64))
    if not row or not matched:
        audit(None, "login:" + username, "failed")
        raise ValueError("账号或密码错误")
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    with connection() as db:
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), row[0], hashlib.sha256(csrf.encode()).hexdigest(), now + SESSION_SECONDS, now))
    audit(row[0], "login", "ok")
    return token, csrf, row[0]


def session(token: str):
    if not token:
        return None
    now = int(time.time())
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connection() as db:
        row = db.execute("SELECT s.user_id,s.csrf_hash,s.expires_at,s.last_seen,u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (digest,)).fetchone()
        if not row:
            return None
        if row[2] <= now or row[3] + IDLE_SECONDS <= now:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest,))
            return None
        db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, digest))
    return {"user_id": row[0], "csrf_hash": row[1], "username": row[4]}


def valid_csrf(session_data, csrf: str) -> bool:
    return bool(csrf) and hmac.compare_digest(hashlib.sha256(csrf.encode()).hexdigest(), session_data["csrf_hash"])


def issue_csrf(token: str) -> str:
    csrf = secrets.token_urlsafe(32)
    with connection() as db:
        db.execute("UPDATE sessions SET csrf_hash=? WHERE token_hash=?",
                   (hashlib.sha256(csrf.encode()).hexdigest(), hashlib.sha256(token.encode()).hexdigest()))
    return csrf


def logout(token: str) -> None:
    with connection() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def _cipher():
    key = os.environ.get("ASW_MASTER_KEY", "").encode("ascii")
    if not key:
        if os.environ.get("ASW_REQUIRE_EXTERNAL_KEY") == "1":
            raise RuntimeError("服务器部署必须通过 ASW_MASTER_KEY 提供主密钥")
        with _key_lock:
            KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            try:
                with KEY_PATH.open("xb") as output:
                    output.write(Fernet.generate_key())
                os.chmod(KEY_PATH, 0o600)
            except FileExistsError:
                pass
            key = KEY_PATH.read_bytes().strip()
    return Fernet(key)


def save_ai_settings(user_id: int, settings: dict) -> None:
    encrypted = _cipher().encrypt(settings["api_key"].encode("utf-8"))
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO ai_settings VALUES(?,?,?,?)",
                   (user_id, settings["base_url"], settings["model"], encrypted))


def load_ai_settings(user_id: int):
    with connection() as db:
        row = db.execute("SELECT base_url,model,encrypted_key FROM ai_settings WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return None
    try:
        key = _cipher().decrypt(row[2]).decode("utf-8")
    except InvalidToken as error:
        raise ValueError("AI 密钥无法解密，请管理员恢复主密钥备份") from error
    return {"base_url": row[0], "model": row[1], "api_key": key}


def delete_ai_settings(user_id: int):
    with connection() as db:
        db.execute("DELETE FROM ai_settings WHERE user_id=?", (user_id,))
