"""Short-lived extraction jobs and aggregate demo statistics."""

import time
from threading import Lock, Thread
from uuid import uuid4

from app.graph import extract
from app.diagnostics import record_error
from app.state import FIELDS
from app.security import CURRENT_USER


STAGES = ("read", "prepare", "extract", "normalize", "complete")
_lock = Lock()
_jobs: dict[str, dict] = {}
_stats = {"completed": 0, "failed": 0, "rules": 0, "ai": 0, "duration_ms": 0, "filled_fields": 0}
_user_stats: dict[int, dict] = {}
_JOB_TTL_SECONDS = 15 * 60
_MAX_ACTIVE_JOBS = 2


def _prune(now: float) -> None:
    expired = [job_id for job_id, job in _jobs.items() if job["finished_at"] is not None and now - job["finished_at"] > _JOB_TTL_SECONDS]
    for job_id in expired:
        del _jobs[job_id]


def start_job(documents: list[dict], mode: str) -> str:
    if mode not in {"rules", "ai"}:
        raise ValueError("无效的提取模式")
    now = time.monotonic()
    user_id = CURRENT_USER.get()
    with _lock:
        _prune(now)
        if sum(job["status"] == "running" for job in _jobs.values()) >= _MAX_ACTIVE_JOBS:
            raise ValueError("已有提取任务正在运行，请等待完成后再试")
        job_id = uuid4().hex
        _jobs[job_id] = {"user_id": user_id, "status": "running", "stage": "read", "detail": "任务已提交，准备读取单据", "started_at": now,
                         "finished_at": None, "mode": mode, "result": None, "error": None,
                         "events": [{"stage": "read", "detail": "任务已提交，准备读取单据", "elapsed_ms": 0}]}
    Thread(target=_run_job, args=(job_id, documents, mode, user_id), daemon=True).start()
    return job_id


def _run_job(job_id: str, documents: list[dict], mode: str, user_id=None) -> None:
    context_token = CURRENT_USER.set(user_id)
    def progress(stage: str, detail: str) -> None:
        if stage not in STAGES:
            return
        with _lock:
            job = _jobs[job_id]
            job["stage"] = stage
            job["detail"] = detail
            job["events"].append({"stage": stage, "detail": detail, "elapsed_ms": round((time.monotonic() - job["started_at"]) * 1000)})

    try:
        result = extract(documents, mode, on_progress=progress)
    except Exception as error:
        record_error("extraction_failed", error, job_id=job_id)
        with _lock:
            job = _jobs[job_id]
            job["status"] = "failed"
            job["error"] = str(error)
            job["error_code"] = f"{job['stage']}_failed"
            job["finished_at"] = time.monotonic()
            _stats["failed"] += 1
            _stats[mode] += 1
            if user_id is not None:
                stats = _user_stats.setdefault(user_id, dict.fromkeys(_stats, 0))
                stats["failed"] += 1
                stats[mode] += 1
    else:
        progress("complete", "提取完成，等待人工核对")
        with _lock:
            job = _jobs[job_id]
            job["status"] = "completed"
            job["result"] = result
            job["finished_at"] = time.monotonic()
            _stats["completed"] += 1
            _stats[mode] += 1
            _stats["duration_ms"] += round((job["finished_at"] - job["started_at"]) * 1000)
            _stats["filled_fields"] += sum(bool(result["fields"][field].get("value")) for field in FIELDS)
            if user_id is not None:
                stats = _user_stats.setdefault(user_id, dict.fromkeys(_stats, 0))
                stats["completed"] += 1
                stats[mode] += 1
                stats["duration_ms"] += round((job["finished_at"] - job["started_at"]) * 1000)
                stats["filled_fields"] += sum(bool(result["fields"][field].get("value")) for field in FIELDS)
    finally:
        CURRENT_USER.reset(context_token)


def get_job(job_id: str) -> dict:
    with _lock:
        _prune(time.monotonic())
        job = _jobs.get(job_id)
        if job is None:
            raise ValueError("提取任务不存在或已过期，请重新提交")
        if job["user_id"] != CURRENT_USER.get():
            raise ValueError("提取任务不存在或已过期，请重新提交")
        elapsed_ms = round(((job["finished_at"] or time.monotonic()) - job["started_at"]) * 1000)
        return {"status": job["status"], "stage": job["stage"], "detail": job["detail"],
                "elapsed_ms": elapsed_ms, "events": list(job["events"]), "result": job["result"], "error": job["error"],
                "error_code": job.get("error_code")}


def get_stats() -> dict:
    with _lock:
        stats = _user_stats.get(CURRENT_USER.get(), dict.fromkeys(_stats, 0)) if CURRENT_USER.get() is not None else _stats
        completed = stats["completed"]
        failed = stats["failed"]
        return {"total": completed + failed, "completed": completed, "failed": failed,
                "ai": stats["ai"], "rules": stats["rules"],
                "average_ms": round(stats["duration_ms"] / completed) if completed else 0,
                "filled_fields": stats["filled_fields"],
                "field_rate": round(stats["filled_fields"] / (completed * len(FIELDS)) * 100) if completed else 0}
