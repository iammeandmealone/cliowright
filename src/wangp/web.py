from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from wangp.config import load_config
from wangp.instructor import InstructorError, configured, instruct, llm_config
from wangp.jobs import STORE, start_script_job
from wangp.script import parse_script, render_markdown, script_to_pipeline
from wangp.settings import catalog

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="wangp", version="0.1.0")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ScriptIn(BaseModel):
    text: str


class InstructIn(BaseModel):
    brief: str
    script: str | None = None
    notes: str | None = None


class RunIn(BaseModel):
    text: str | None = None
    script: dict[str, Any] | None = None
    dry_run: bool = False


def _parse_or_400(text: str) -> dict[str, Any]:
    try:
        return parse_script(text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="web UI missing")
    return FileResponse(index_path)


@app.get("/api/health")
def health() -> dict[str, Any]:
    cfg = llm_config()
    return {
        "ok": True,
        "instructor": configured(),
        "model": cfg["model"] if configured() else None,
        "base_url": cfg["base_url"] if configured() else None,
    }


@app.get("/api/settings")
def settings_catalog() -> dict[str, Any]:
    return {"fields": catalog()}


@app.post("/api/script/parse")
def parse_endpoint(body: ScriptIn) -> dict[str, Any]:
    script = _parse_or_400(body.text)
    return {
        "script": script,
        "markdown": render_markdown(script),
        "pipeline": script_to_pipeline(script),
    }


@app.post("/api/instruct")
def instruct_endpoint(body: InstructIn) -> dict[str, Any]:
    try:
        result = instruct(body.brief, script=body.script, notes=body.notes)
    except InstructorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/api/run")
def run_endpoint(body: RunIn) -> dict[str, Any]:
    if body.script:
        script = body.script
    elif body.text:
        script = _parse_or_400(body.text)
    else:
        raise HTTPException(status_code=400, detail="text or script required")
    if not script.get("shots"):
        raise HTTPException(status_code=400, detail="script has no shots")
    config = load_config()
    job = start_script_job(script, config=config, dry_run=body.dry_run)
    return {"job": job}


@app.get("/api/jobs")
def list_jobs() -> dict[str, Any]:
    return {"jobs": STORE.list()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def create_app() -> FastAPI:
    return app
