from __future__ import annotations

import importlib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from wangp.config import load_config, resolve_output_dir, resolve_root, wan_cli_args
from wangp.events import Emitter


class WanGPNotFound(FileNotFoundError):
    pass


class WanGPImportError(RuntimeError):
    pass


def _ensure_root_on_path(root: Path) -> None:
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def import_api(root: Path):
    _ensure_root_on_path(root)
    try:
        return importlib.import_module("shared.api")
    except ModuleNotFoundError as exc:
        raise WanGPImportError(
            f"could not import shared.api from {root}. "
            "Install WanGP and set root / WANGP_ROOT."
        ) from exc


@dataclass
class JobResult:
    success: bool
    generated_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
    elapsed: float = 0.0
    raw: Any = None


class Session:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        emitter: Emitter | None = None,
        output_dir: Path | None = None,
        console_output: bool = False,
    ) -> None:
        self.config = config if config is not None else load_config()
        self.emitter = emitter or Emitter()
        self._root: Path | None = None
        self._output_dir = output_dir
        self.console_output = console_output
        self._api = None
        self._session = None

    @property
    def root(self) -> Path:
        if self._root is None:
            root = resolve_root(self.config)
            if not (root / "wgp.py").exists() and not (root / "shared" / "api.py").exists():
                raise WanGPNotFound(f"WanGP not found at {root}")
            self._root = root
        return self._root

    @property
    def output_dir(self) -> Path:
        if self._output_dir is None:
            self._output_dir = resolve_output_dir(self.config)
        return self._output_dir

    def connect(self):
        if self._session is not None:
            return self._session
        api = import_api(self.root)
        cli_args = wan_cli_args(self.config)
        self._api = api
        self._session = api.init(
            root=self.root,
            output_dir=self.output_dir,
            cli_args=cli_args,
            console_output=self.console_output,
        )
        return self._session

    def list_models(
        self,
        query: str | None = None,
        main_output: str | list[str] | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        session = self.connect()
        kwargs: dict[str, Any] = {}
        if query:
            kwargs["query"] = query
        if main_output:
            kwargs["main_output"] = main_output
        if limit is not None:
            kwargs["limit"] = limit
        return list(session.list_model_metadata(**kwargs))

    def defaults(self, model_type: str) -> dict[str, Any]:
        session = self.connect()
        return dict(session.get_default_settings(model_type))

    def schema(self, model_type: str) -> dict[str, Any] | None:
        session = self.connect()
        return session.get_model_schema(model_type)

    def generate(
        self,
        settings: dict[str, Any],
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> JobResult:
        session = self.connect()
        started = time.monotonic()
        job = session.submit_task(settings)
        try:
            for event in job.events.iter(timeout=0.2):
                kind = getattr(event, "kind", None)
                data = getattr(event, "data", None)
                if kind == "progress":
                    payload = {
                        "phase": getattr(data, "phase", None),
                        "progress": getattr(data, "progress", None),
                        "step": getattr(data, "current_step", None),
                        "total": getattr(data, "total_steps", None),
                        "status": getattr(data, "status", None),
                    }
                    self.emitter.emit("progress", **payload)
                    if on_progress:
                        on_progress(payload)
                elif kind == "status":
                    message = data if isinstance(data, str) else str(data or "")
                    if message:
                        self.emitter.emit("status", message=message)
                elif kind == "stream":
                    text = getattr(data, "text", None) or str(data or "")
                    if text:
                        self.emitter.emit("status", message=text.rstrip())
        except Exception:
            pass
        raw = job.result()
        elapsed = time.monotonic() - started
        files = [str(path) for path in (getattr(raw, "generated_files", None) or [])]
        errors = []
        for error in getattr(raw, "errors", None) or []:
            message = getattr(error, "message", None) or str(error)
            errors.append(message)
        success = bool(getattr(raw, "success", False)) and not errors
        cancelled = bool(getattr(raw, "cancelled", False))
        for path in files:
            self.emitter.emit("file", path=path)
        if errors:
            for message in errors:
                self.emitter.emit("error", message=message)
        self.emitter.emit(
            "done",
            success=success,
            elapsed=_format_elapsed(elapsed),
            files=files,
            cancelled=cancelled,
        )
        return JobResult(
            success=success,
            generated_files=files,
            errors=errors,
            cancelled=cancelled,
            elapsed=elapsed,
            raw=raw,
        )

    def process_queue(self, source: str | Path, dry_run: bool = False) -> JobResult:
        session = self.connect()
        started = time.monotonic()
        path = Path(source)
        if dry_run:
            self.emitter.emit("status", message=f"dry-run {path}")
            return JobResult(success=True, elapsed=time.monotonic() - started)
        job = session.submit(str(path))
        raw = job.result()
        elapsed = time.monotonic() - started
        files = [str(item) for item in (getattr(raw, "generated_files", None) or [])]
        errors = [
            getattr(error, "message", None) or str(error)
            for error in (getattr(raw, "errors", None) or [])
        ]
        success = bool(getattr(raw, "success", False)) and not errors
        for item in files:
            self.emitter.emit("file", path=item)
        self.emitter.emit(
            "done",
            success=success,
            elapsed=_format_elapsed(elapsed),
            files=files,
        )
        return JobResult(
            success=success,
            generated_files=files,
            errors=errors,
            elapsed=elapsed,
            raw=raw,
        )


def _format_elapsed(seconds: float) -> str:
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{seconds:.1f}s"
