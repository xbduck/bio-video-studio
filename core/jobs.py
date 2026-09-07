"""后台任务状态（配音 / 合成），供前端轮询。"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}


def start(job_id: str, kind: str, total: int = 0) -> None:
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "running",
            "progress": 0,
            "total": total,
            "message": "开始…",
            "error": "",
            "result": None,
            "started_at": time.time(),
        }


def update(job_id: str, progress: int = None, message: str = None) -> None:
    with _LOCK:
        job = _JOBS.setdefault(job_id, {})
        if progress is not None:
            job["progress"] = progress
        if message is not None:
            job["message"] = message


def finish(job_id: str, result: dict = None) -> None:
    with _LOCK:
        job = _JOBS.setdefault(job_id, {})
        job.update({"status": "done", "progress": 100, "message": "完成", "result": result or {}})


def fail(job_id: str, error: str) -> None:
    with _LOCK:
        job = _JOBS.setdefault(job_id, {})
        job.update({"status": "failed", "error": error, "message": "失败"})


def get(job_id: str) -> dict | None:
    with _LOCK:
        return dict(_JOBS.get(job_id)) if job_id in _JOBS else None
