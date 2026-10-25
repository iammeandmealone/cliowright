from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from wangp.script import parse_script, render_markdown
from wangp.settings import catalog

SYSTEM_PROMPT = """You are the instructor agent for wangp, a headless WanGP video pipeline.
You turn a brief into a multi-shot video script the pipeline can run.

Rules:
- Output a video script, not chat.
- Prefer Markdown with a title, optional logline, shared defaults, then ## Shot N headings.
- Each shot needs a visual prompt (what the camera sees) and optional settings as key: value lines.
- Known settings: model_type, resolution, video_length, num_inference_steps, seed, force_fps, image_start, image_end, image_refs, image_prompt_type, video_source, video_prompt_type, negative_prompt, sliding_window_size, activated_loras, loras_multipliers.
- Keep each shot short enough for one generation window (about 4-8 seconds unless the user asks for longer).
- For a sequence that should continue, set continue: previous on later shots.
- Do not invent API keys or file paths the user did not give.
- If the user pastes an existing script, revise it instead of starting over.
- Put cinematic camera language in the prompt: shot size, motion, lighting.
- Defaults belong once at the top (model_type, resolution, steps, seed), not repeated unless a shot overrides them.
"""


class InstructorError(RuntimeError):
    pass


def _load_dotenv() -> None:
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("USER_LLM_"):
            continue
        if key not in os.environ or os.environ.get(key) == "":
            os.environ[key] = value.strip().strip('"').strip("'")


def llm_config() -> dict[str, str]:
    _load_dotenv()
    return {
        "api_key": os.getenv("USER_LLM_API_KEY") or "",
        "base_url": (os.getenv("USER_LLM_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/"),
        "model": os.getenv("USER_LLM_MODEL") or "deepseek-chat",
    }


def configured() -> bool:
    return bool(llm_config()["api_key"])


def _endpoint(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def complete(messages: list[dict[str, str]], timeout: int = 60) -> str:
    cfg = llm_config()
    if not cfg["api_key"]:
        raise InstructorError(
            "USER_LLM_API_KEY is not set. Copy .env.example to .env and add your own key."
        )
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.6,
    }
    request = urllib.request.Request(
        _endpoint(cfg["base_url"]),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise InstructorError(f"LLM HTTP {exc.code}: {detail[:400]}") from exc
    except urllib.error.URLError as exc:
        raise InstructorError(f"LLM unreachable: {exc.reason}") from exc
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise InstructorError("LLM response missing choices[0].message.content") from exc


def _extract_script(text: str) -> str:
    fenced = re.search(r"```(?:markdown|md|yaml|json)?\s*([\s\S]*?)```", text)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def instruct(
    brief: str,
    script: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    user_parts = [f"Brief:\n{brief.strip()}"]
    if script and script.strip():
        user_parts.append(f"Current script to revise:\n{script.strip()}")
    if notes and notes.strip():
        user_parts.append(f"Notes:\n{notes.strip()}")
    fields = ", ".join(field["key"] for field in catalog())
    user_parts.append(f"Allowed setting keys: {fields}")
    user_parts.append("Return only the script.")
    raw = complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]
    )
    markdown = _extract_script(raw)
    parsed = parse_script(markdown)
    return {
        "markdown": render_markdown(parsed) if parsed.get("shots") else markdown,
        "script": parsed,
        "raw": raw,
        "model": llm_config()["model"],
    }
