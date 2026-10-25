from __future__ import annotations

import io
import json
import threading
import time
import uuid
from typing import Any, Callable

from wangp.events import Emitter
from wangp.pipeline import PipelineRunner
from wangp.runtime import Session
from wangp.script import script_to_pipeline


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        record = {
            "id": job_id,
            "status": "queued",
            "created": time.time(),
            "events": [],
            "outputs": [],
            "error": None,
            **payload,
        }
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return json.loads(json.dumps(job)) if job else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [json.loads(json.dumps(job)) for job in self._jobs.values()]
        jobs.sort(key=lambda item: item.get("created") or 0, reverse=True)
        return jobs

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["events"].append(event)
            if event.get("type") == "file" and event.get("path"):
                job["outputs"].append(event["path"])

    def finish(self, job_id: str, success: bool, error: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["status"] = "done" if success else "error"
            job["error"] = error
            job["finished"] = time.time()


STORE = JobStore()


class MemoryEmitter(Emitter):
    def __init__(self, job_id: str) -> None:
        super().__init__(fmt="json", stream=io.StringIO())
        self.job_id = job_id

    def emit(self, type: str, **data: Any):
        event = super().emit(type, **data)
        STORE.append_event(self.job_id, event.to_dict())
        return event


def start_script_job(
    script: dict[str, Any],
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
    runner_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    pipeline = script_to_pipeline(script)
    job = STORE.create(
        {
            "title": script.get("title"),
            "pipeline": pipeline,
            "dry_run": dry_run,
        }
    )
    thread = threading.Thread(
        target=_run_job,
        args=(job["id"], pipeline, config, dry_run, runner_factory),
        daemon=True,
    )
    thread.start()
    return job


def _run_job(
    job_id: str,
    pipeline: dict[str, Any],
    config: dict[str, Any] | None,
    dry_run: bool,
    runner_factory: Callable[..., Any] | None,
) -> None:
    STORE.get(job_id)
    with STORE._lock:
        if job_id in STORE._jobs:
            STORE._jobs[job_id]["status"] = "running"
    emitter = MemoryEmitter(job_id)
    try:
        if runner_factory:
            result = runner_factory(pipeline, dry_run=dry_run, emitter=emitter)
        else:
            session = Session(config=config, emitter=emitter)
            result = PipelineRunner(session, emitter=emitter).run(pipeline, dry_run=dry_run)
        success = bool(result.get("success"))
        STORE.finish(job_id, success, None if success else "pipeline failed")
    except Exception as exc:
        emitter.emit("error", message=str(exc))
        STORE.finish(job_id, False, str(exc))
