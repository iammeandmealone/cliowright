from __future__ import annotations

import json
import re
from typing import Any

import yaml

from wangp.settings import normalize_settings

HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
KV = re.compile(r"^([A-Za-z][\w.-]*)\s*[:=]\s*(.*)$")
SHOT_TITLE = re.compile(r"^(shot|scene|clip)\s*(\d+)?\s*[:.-]?\s*(.*)$", re.I)


def parse_script(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("script is empty")
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(stripped)
        return _from_mapping(data if isinstance(data, dict) else {"shots": data})
    if stripped.startswith("---") or re.match(r"^(name|title|shots|defaults)\s*:", stripped):
        data = yaml.safe_load(stripped)
        if isinstance(data, dict) and ("shots" in data or "steps" in data):
            return _from_mapping(data)
    return _from_markdown(stripped)


def _from_mapping(data: dict[str, Any]) -> dict[str, Any]:
    shots_raw = data.get("shots") or data.get("steps") or []
    shots = []
    for index, item in enumerate(shots_raw, start=1):
        if isinstance(item, str):
            item = {"prompt": item}
        if not isinstance(item, dict):
            continue
        shot = normalize_settings(item)
        shot["id"] = str(item.get("id") or f"shot{index}")
        shot["title"] = item.get("title") or item.get("name") or shot["id"]
        if item.get("prompt") and "prompt" not in shot:
            shot["prompt"] = item["prompt"]
        shots.append(shot)
    defaults = normalize_settings(data.get("defaults") or data.get("settings") or {})
    return {
        "title": data.get("title") or data.get("name") or "untitled",
        "logline": data.get("logline") or data.get("description") or "",
        "defaults": defaults,
        "shots": shots,
    }


def _from_markdown(text: str) -> dict[str, Any]:
    lines = text.replace("\r\n", "\n").split("\n")
    title = "untitled"
    logline = ""
    defaults: dict[str, Any] = {}
    shots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    body: list[str] = []
    preamble: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is None:
            return
        prompt = current.get("prompt") or "\n".join(body).strip()
        if prompt:
            current["prompt"] = prompt
        shots.append(normalize_settings(current) | {
            "id": current.get("id") or f"shot{len(shots) + 1}",
            "title": current.get("title") or f"Shot {len(shots) + 1}",
            "prompt": current.get("prompt") or "",
        })
        current = None
        body = []

    for raw in lines:
        line = raw.rstrip()
        heading = HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            name = heading.group(2).strip()
            shot_match = SHOT_TITLE.match(name)
            if level == 1 and not shots and current is None:
                title = name
                continue
            if shot_match or name.lower().startswith(("shot", "scene", "clip")):
                flush()
                number = shot_match.group(2) if shot_match else None
                rest = (shot_match.group(3) if shot_match else name).strip(" :-")
                current = {
                    "id": f"shot{number}" if number else f"shot{len(shots) + 1}",
                    "title": rest or (f"Shot {number}" if number else f"Shot {len(shots) + 1}"),
                }
                body = []
                continue
            continue
        kv = KV.match(line.strip())
        if kv:
            key = kv.group(1)
            value = _parse_value(kv.group(2))
            if current is None:
                if key.lower() in {"title", "name"}:
                    title = str(value)
                elif key.lower() in {"logline", "description"}:
                    logline = str(value)
                else:
                    defaults[key] = value
            else:
                current[key] = value
            continue
        if line.strip() == "---":
            continue
        if current is None:
            if line.strip():
                preamble.append(line.strip())
        else:
            body.append(line)

    flush()
    if not logline and preamble:
        logline = " ".join(preamble)
    if not shots and preamble:
        shots.append({
            "id": "shot1",
            "title": "Shot 1",
            "prompt": "\n".join(preamble),
        })
    return {
        "title": title,
        "logline": logline,
        "defaults": normalize_settings(defaults),
        "shots": shots,
    }


def _parse_value(raw: str) -> Any:
    text = raw.strip().strip('"').strip("'")
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    if "," in text and all(part.strip() for part in text.split(",")):
        return [part.strip() for part in text.split(",")]
    return text


def script_to_pipeline(script: dict[str, Any]) -> dict[str, Any]:
    defaults = dict(script.get("defaults") or {})
    steps = []
    previous_id = None
    for index, shot in enumerate(script.get("shots") or [], start=1):
        step_id = str(shot.get("id") or f"shot{index}")
        settings = {key: value for key, value in shot.items() if key not in {"id", "title"}}
        if shot.get("continue") in {True, "previous", "last"} and previous_id:
            settings["video_source"] = f"${{steps.{previous_id}.files.0}}"
            flags = str(settings.get("image_prompt_type") or "")
            if "V" not in flags:
                settings["image_prompt_type"] = flags + "V"
            settings.pop("continue", None)
        steps.append({
            "id": step_id,
            "kind": "generate",
            "model": settings.pop("model_type", None) or defaults.get("model_type"),
            "prompt": settings.pop("prompt", ""),
            "settings": settings,
        })
        previous_id = step_id
    return {
        "name": script.get("title") or "script",
        "defaults": defaults,
        "steps": steps,
    }


def render_markdown(script: dict[str, Any]) -> str:
    lines = [f"# {script.get('title') or 'untitled'}"]
    if script.get("logline"):
        lines.append("")
        lines.append(script["logline"])
    defaults = script.get("defaults") or {}
    if defaults:
        lines.append("")
        for key, value in defaults.items():
            lines.append(f"{key}: {value}")
    for index, shot in enumerate(script.get("shots") or [], start=1):
        lines.append("")
        lines.append(f"## Shot {index}: {shot.get('title') or shot.get('id')}")
        for key, value in shot.items():
            if key in {"id", "title", "prompt"}:
                continue
            lines.append(f"{key}: {value}")
        if shot.get("prompt"):
            lines.append("")
            lines.append(shot["prompt"])
    lines.append("")
    return "\n".join(lines)
