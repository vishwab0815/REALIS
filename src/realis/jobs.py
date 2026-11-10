"""Background analysis jobs: one GPU worker, a queue, live progress.

Video analysis can take minutes, longer than a browser should hold a request
open. Uploads become jobs; clients poll for progress and the final result.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from realis.pipeline import IntegrityError

log = logging.getLogger("realis.jobs")

JobStatus = Literal["queued", "running", "done", "error"]
# runner(path, original_name, deep, progress) -> result payload
Runner = Callable[[Path, str, bool, Callable[[str, float], None]], dict[str, Any]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(BaseModel):
    id: str
    name: str
    size_bytes: int
    deep: bool
    status: JobStatus = "queued"
    stage: str = "Queued"
    progress: float = 0.0
    queue_position: int = 0
    created_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class JobManager:
    def __init__(self, runner: Runner, workers: int = 1, history: int = 200):
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="analysis")
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._history = history

    def submit(self, upload: Path, name: str, size: int, deep: bool) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], name=name, size_bytes=size, deep=deep)
        with self._lock:
            self._jobs[job.id] = job
            self._prune()
        self._pool.submit(self._run, job.id, upload)
        return self.get(job.id)  # type: ignore[return-value]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            snapshot = job.model_copy()
            if snapshot.status == "queued":
                snapshot.queue_position = sum(
                    1 for j in self._jobs.values() if j.status in ("queued", "running") and j.created_at < job.created_at)
            return snapshot

    def active(self) -> list[Job]:
        with self._lock:
            ids = [j.id for j in self._jobs.values() if j.status in ("queued", "running")]
        return [j for j in (self.get(i) for i in ids) if j]

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in fields.items():
                    setattr(job, k, v)

    def _run(self, job_id: str, upload: Path) -> None:
        job = self.get(job_id)
        if job is None:
            return
        self._update(job_id, status="running", started_at=_now(), stage="Starting")
        try:
            result = self._runner(upload, job.name, job.deep,
                                  lambda stage, f: self._update(job_id, stage=stage, progress=round(f, 4)))
            self._update(job_id, status="done", stage="Done", progress=1.0, result=result)
        except (ValueError, IntegrityError) as e:
            self._update(job_id, status="error", stage="Failed", error=str(e))
        except Exception:
            log.exception("analysis job %s failed", job_id)
            self._update(job_id, status="error", stage="Failed",
                         error="Internal error during analysis; see the server log.")
        finally:
            self._update(job_id, finished_at=_now())
            upload.unlink(missing_ok=True)

    def _prune(self) -> None:
        finished = [i for i, j in self._jobs.items() if j.status in ("done", "error")]
        for i in finished[: max(0, len(self._jobs) - self._history)]:
            del self._jobs[i]
