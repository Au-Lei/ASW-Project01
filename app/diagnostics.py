"""Best-effort diagnostics without keys, document contents, or exception values."""

import logging
import traceback
from logging.handlers import RotatingFileHandler
from threading import Lock

from app.state import PROJECT_ROOT

_lock = Lock()


def record_error(event: str, error: BaseException, *, job_id: str = "") -> None:
    try:
        with _lock:
            logger = logging.getLogger("asw.diagnostics")
            if not logger.handlers:
                directory = PROJECT_ROOT / "logs"
                directory.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(directory / "app.log", maxBytes=1_000_000,
                                              backupCount=2, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                logger.addHandler(handler)
                logger.setLevel(logging.ERROR)
                logger.propagate = False
            # Stack locations only: exception messages can contain customer data or secrets.
            frames = "\n".join(f"{frame.filename}:{frame.lineno} in {frame.name}"
                               for frame in traceback.extract_tb(error.__traceback__))
            logger.error("event=%s job=%s type=%s\n%s", event, job_id,
                         type(error).__name__, frames)
    except OSError:
        pass  # Diagnostics must not turn a recoverable request into a new failure.
