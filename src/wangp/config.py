from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA = "https://wangp.dev/config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "$schema": SCHEMA,
    "root": "",
    "output_dir": "outputs",
    "config_dir": "",
    "profile": 4,
    "attention": "sdpa",
    "offline": False,
    "cli_args": [],
    "defaults": {
        "model": "",
        "resolution": "832x480",
        "steps": 8,
        "video_length": "5s",
        "seed": -1,
    },
}


def config_search_paths() -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("WANGP_CONFIG")
    if env_path:
        paths.append(Path(env_path).expanduser())
    cwd = Path.cwd()
    paths.append(cwd / "wangp.json")
    paths.append(cwd / "wangp.jsonc")
    home = Path.home() / ".config" / "wangp"
    paths.append(home / "wangp.json")
    paths.append(home / "wangp.jsonc")
    return paths


def load_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonc":
        text = _strip_jsonc(text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"config must be an object: {path}")
    return data


def _strip_jsonc(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < n and text[i] not in "\n\r":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i < n - 1 and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(path: Path | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"config not found: {path}")
        return merge(config, load_json(path))
    for candidate in reversed(config_search_paths()):
        if candidate.exists() and candidate.is_file():
            config = merge(config, load_json(candidate))
    env_root = os.environ.get("WANGP_ROOT")
    if env_root:
        config["root"] = env_root
    env_out = os.environ.get("WANGP_OUTPUT_DIR")
    if env_out:
        config["output_dir"] = env_out
    return config


def resolve_root(config: dict[str, Any]) -> Path:
    root = str(config.get("root") or "").strip()
    if root:
        return Path(root).expanduser().resolve()
    env = os.environ.get("WANGP_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    for marker in ("wgp.py", "shared/api.py"):
        candidate = Path.cwd() / marker
        if candidate.exists():
            return Path.cwd().resolve()
    parent = Path.cwd().parent / "Wan2GP"
    if (parent / "wgp.py").exists():
        return parent.resolve()
    sibling = Path.cwd() / "Wan2GP"
    if (sibling / "wgp.py").exists():
        return sibling.resolve()
    raise FileNotFoundError(
        "WanGP root not found. Set root in wangp.json or WANGP_ROOT."
    )


def resolve_output_dir(config: dict[str, Any], override: str | None = None) -> Path:
    raw = override or config.get("output_dir") or "outputs"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def wan_cli_args(config: dict[str, Any], extra: list[str] | None = None) -> list[str]:
    args: list[str] = []
    profile = config.get("profile")
    if profile is not None and profile != "":
        args.extend(["--profile", str(profile)])
    attention = config.get("attention")
    if attention:
        args.extend(["--attention", str(attention)])
    if config.get("offline"):
        args.append("--offline")
    extra_cfg = config.get("cli_args") or []
    if isinstance(extra_cfg, list):
        args.extend(str(item) for item in extra_cfg)
    if extra:
        args.extend(extra)
    return args


def write_example(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    example = deepcopy(DEFAULT_CONFIG)
    example["root"] = str(Path.home() / "Wan2GP")
    path.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")
