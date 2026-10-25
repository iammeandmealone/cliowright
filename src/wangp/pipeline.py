from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from wangp.events import Emitter
from wangp.runtime import JobResult, Session

INTERPOLATION = re.compile(r"\$\{([^}]+)\}")


class PipelineError(ValueError):
    pass


def load_pipeline(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PipelineError(f"pipeline must be a mapping: {path}")
    if "steps" not in data or not isinstance(data["steps"], list):
        raise PipelineError("pipeline requires a steps list")
    return data


def _lookup(context: dict[str, Any], expr: str) -> Any:
    current: Any = context
    for part in expr.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise PipelineError(f"unknown interpolation: {expr}")
    return current


def interpolate(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        matches = list(INTERPOLATION.finditer(value))
        if not matches:
            return value
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return _lookup(context, matches[0].group(1))
        def repl(match: re.Match[str]) -> str:
            return str(_lookup(context, match.group(1)))
        return INTERPOLATION.sub(repl, value)
    if isinstance(value, list):
        return [interpolate(item, context) for item in value]
    if isinstance(value, dict):
        return {key: interpolate(item, context) for key, item in value.items()}
    return value


def merge_settings(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class PipelineRunner:
    def __init__(self, session: Session, emitter: Emitter | None = None) -> None:
        self.session = session
        self.emitter = emitter or session.emitter

    def run(
        self,
        pipeline: dict[str, Any],
        params: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "params": params or {},
            "pipeline": pipeline.get("name") or "pipeline",
            "steps": {},
            "outputs": [],
        }
        defaults = pipeline.get("defaults") or {}
        steps = pipeline["steps"]
        results: list[dict[str, Any]] = []
        failed = False
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, dict):
                raise PipelineError(f"step {index} must be a mapping")
            step = interpolate(raw_step, context)
            step_id = str(step.get("id") or f"step{index}")
            kind = str(step.get("kind") or "generate")
            self.emitter.emit(
                "step",
                index=index,
                count=len(steps),
                id=step_id,
                kind=kind,
            )
            if dry_run:
                record = {"id": step_id, "kind": kind, "dry_run": True, "settings": step}
                results.append(record)
                context["steps"][step_id] = record
                continue
            if kind == "generate":
                record = self._run_generate(step, defaults, context)
            elif kind == "settings":
                record = self._run_settings_file(step)
            elif kind == "queue":
                record = self._run_queue(step)
            else:
                raise PipelineError(f"unsupported step kind: {kind}")
            results.append(record)
            context["steps"][step_id] = record
            files = record.get("files") or []
            context["outputs"].extend(files)
            if files:
                context["last_file"] = files[-1]
            if not record.get("success", False):
                failed = True
                if not step.get("continue_on_error"):
                    break
        return {
            "success": not failed,
            "results": results,
            "outputs": context["outputs"],
        }

    def _run_generate(
        self,
        step: dict[str, Any],
        defaults: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        settings = merge_settings(defaults, step.get("settings") or {})
        if "model" in step and "model_type" not in settings:
            settings["model_type"] = step["model"]
        if "prompt" in step and "prompt" not in settings:
            settings["prompt"] = step["prompt"]
        if not settings.get("model_type"):
            raise PipelineError("generate step requires model or settings.model_type")
        if not settings.get("prompt"):
            raise PipelineError("generate step requires prompt")
        result = self.session.generate(settings)
        return _result_record(step, result)

    def _run_settings_file(self, step: dict[str, Any]) -> dict[str, Any]:
        path = step.get("path")
        if not path:
            raise PipelineError("settings step requires path")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            files: list[str] = []
            errors: list[str] = []
            success = True
            for item in data:
                result = self.session.generate(item)
                files.extend(result.generated_files)
                errors.extend(result.errors)
                success = success and result.success
            return {
                "id": step.get("id"),
                "kind": "settings",
                "success": success,
                "files": files,
                "errors": errors,
            }
        if not isinstance(data, dict):
            raise PipelineError("settings file must be an object or list")
        result = self.session.generate(data)
        return _result_record(step, result)

    def _run_queue(self, step: dict[str, Any]) -> dict[str, Any]:
        path = step.get("path")
        if not path:
            raise PipelineError("queue step requires path")
        result = self.session.process_queue(path)
        return _result_record(step, result)


def _result_record(step: dict[str, Any], result: JobResult) -> dict[str, Any]:
    return {
        "id": step.get("id"),
        "kind": step.get("kind") or "generate",
        "success": result.success,
        "files": result.generated_files,
        "errors": result.errors,
        "elapsed": result.elapsed,
    }
