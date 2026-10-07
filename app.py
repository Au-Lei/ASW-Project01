"""Run the local booking document MVP with `python app.py`."""

import os

from app.config import load_env
from app.wsgi import serve


if __name__ == "__main__":
    load_env()
    serve(int(os.environ.get("PORT", "8765")))
