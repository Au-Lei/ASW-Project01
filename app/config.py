"""Load local development settings without replacing process environment values."""

import os

from app.state import PROJECT_ROOT


def load_env() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "PORT" and value:
            os.environ.setdefault(key, value)
