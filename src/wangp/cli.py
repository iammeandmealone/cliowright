from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from wangp import __version__
from wangp.config import load_config, write_example
from wangp.events import Emitter
from wangp.instructor import InstructorError
from wangp.pipeline import PipelineError, PipelineRunner, load_pipeline
from wangp.runtime import Session, WanGPImportError, WanGPNotFound


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", help="Path to wangp.json / wangp.jsonc")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Event output format",
    )
    parser.add_argument("--output-dir", help="Override output directory")
    parser.add_argument("--root", help="Override WanGP installation root")
    return parser


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="wangp",
        description="Headless WanGP pipeline. No Gradio, no notebooks.",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"wangp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Write a starter wangp.json", parents=[common])
    init_p.add_argument(
        "--path",
        default="wangp.json",
        help="Where to write the config (default: ./wangp.json)",
    )

    run_p = sub.add_parser(
        "run",
        help="Run a prompt or YAML pipeline (non-interactive)",
        parents=[common],
    )
    run_p.add_argument("target", nargs="?", help="Prompt text or path to .yaml/.yml/.json/.zip")
    run_p.add_argument("--pipeline", "-p", help="YAML pipeline file")
    run_p.add_argument("--model", "-m", help="WanGP model_type")
    run_p.add_argument("--prompt", help="Generation prompt")
    run_p.add_argument("--resolution", help="WxH, e.g. 832x480")
    run_p.add_argument("--steps", type=int, help="Denoising steps")
    run_p.add_argument("--length", help="video_length, frames or Ns")
    run_p.add_argument("--seed", type=int, help="Seed (-1 random)")
    run_p.add_argument("--image", action="append", default=[], help="Start / reference image")
    run_p.add_argument("--settings", help="Exported WanGP settings JSON")
    run_p.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="Pipeline param")
    run_p.add_argument("--dry-run", action="store_true", help="Validate without generating")
    run_p.add_argument("--attach", help="Reserved: attach to a running WanGP MCP server")

    models_p = sub.add_parser("models", help="List WanGP models", parents=[common])
    models_p.add_argument("query", nargs="?", help="Substring / glob query")
    models_p.add_argument("--output", choices=("video", "image", "audio", "world", "3d"))
    models_p.add_argument("--limit", type=int, default=50)

    sub.add_parser("schema", help="Print model schema", parents=[common]).add_argument("model")
    sub.add_parser("defaults", help="Print default settings for a model", parents=[common]).add_argument("model")

    instruct_p = sub.add_parser("instruct", help="Draft a video script with the instructor agent", parents=[common])
    instruct_p.add_argument("brief", nargs="?", help="What the video should be")
    instruct_p.add_argument("--script", help="Existing script file to revise")
    instruct_p.add_argument("--notes", help="Extra constraints for the instructor")
    instruct_p.add_argument("--out", help="Write the drafted script to this path")

    parse_p = sub.add_parser("parse", help="Parse a video script into shots and settings", parents=[common])
    parse_p.add_argument("path", help="Markdown, YAML, or JSON script")

    web_p = sub.add_parser("web", help="Open the script / settings / instructor UI", parents=[common])
    web_p.add_argument("--host", default="0.0.0.0")
    web_p.add_argument("--port", type=int, default=8000)

    serve_p = sub.add_parser(
        "serve",
        help="Start WanGP as a headless MCP server",
        parents=[common],
    )
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default="streamable-http")

    return parser


def _config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.config).expanduser() if args.config else None
    config = load_config(path)
    if args.root:
        config["root"] = args.root
    if args.output_dir:
        config["output_dir"] = args.output_dir
    return config


def _session(args: argparse.Namespace) -> Session:
    config = _config_from_args(args)
    emitter = Emitter(fmt=args.format)
    output_dir = None
    if args.output_dir:
        from wangp.config import resolve_output_dir

        output_dir = resolve_output_dir(config, args.output_dir)
    return Session(config=config, emitter=emitter, output_dir=output_dir)


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if path.exists():
        print(f"already exists: {path}", file=sys.stderr)
        return 1
    write_example(path)
    print(f"wrote {path}")
    return 0


def _parse_params(items: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise PipelineError(f"param must be KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        params[key] = _coerce(value)
    return params


def _coerce(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _settings_from_run(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    defaults = config.get("defaults") or {}
    model = args.model or defaults.get("model")
    prompt = args.prompt
    if args.target and not Path(args.target).exists() and not prompt:
        prompt = args.target
    if args.settings:
        loaded = json.loads(Path(args.settings).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise PipelineError("settings JSON must be an object")
        settings.update(loaded)
    if model:
        settings["model_type"] = model
    if prompt:
        settings["prompt"] = prompt
    resolution = args.resolution or defaults.get("resolution")
    if resolution and "resolution" not in settings:
        settings["resolution"] = resolution
    steps = args.steps if args.steps is not None else defaults.get("steps")
    if steps is not None and "num_inference_steps" not in settings:
        settings["num_inference_steps"] = steps
    length = args.length or defaults.get("video_length")
    if length and "video_length" not in settings:
        settings["video_length"] = length
    seed = args.seed if args.seed is not None else defaults.get("seed")
    if seed is not None and "seed" not in settings:
        settings["seed"] = seed
    if args.image:
        settings["image_start"] = args.image[0]
        flags = settings.get("image_prompt_type") or ""
        if "S" not in flags:
            settings["image_prompt_type"] = flags + "S"
        if len(args.image) > 1:
            settings["image_refs"] = args.image[1:]
    return settings


def cmd_run(args: argparse.Namespace) -> int:
    session = _session(args)
    if args.pipeline:
        pipeline = load_pipeline(Path(args.pipeline))
        params = _parse_params(args.param)
        result = PipelineRunner(session).run(pipeline, params=params, dry_run=args.dry_run)
        return 0 if result["success"] else 1

    target = args.target
    if target:
        path = Path(target)
        suffix = path.suffix.lower()
        if path.exists() and suffix in {".yaml", ".yml"}:
            pipeline = load_pipeline(path)
            params = _parse_params(args.param)
            result = PipelineRunner(session).run(pipeline, params=params, dry_run=args.dry_run)
            return 0 if result["success"] else 1
        if path.exists() and suffix in {".md", ".txt"}:
            from wangp.script import parse_script, script_to_pipeline

            script = parse_script(path.read_text(encoding="utf-8"))
            pipeline = script_to_pipeline(script)
            result = PipelineRunner(session).run(pipeline, dry_run=args.dry_run)
            return 0 if result["success"] else 1
        if path.exists() and suffix in {".zip", ".json"}:
            if args.dry_run and suffix == ".zip":
                session.emitter.emit("status", message=f"dry-run {path}")
                return 0
            if suffix == ".json" and not args.model and not args.prompt:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "steps" in data:
                    result = PipelineRunner(session).run(data, dry_run=args.dry_run)
                    return 0 if result["success"] else 1
                if isinstance(data, dict) and "model_type" in data:
                    if args.dry_run:
                        session.emitter.emit("status", message=f"dry-run settings {path}")
                        return 0
                    result = session.generate(data)
                    return 0 if result.success else 1
            result = session.process_queue(path, dry_run=args.dry_run)
            return 0 if result.success else 1

    settings = _settings_from_run(args, session.config)
    if not settings.get("model_type") or not settings.get("prompt"):
        print("wangp run needs --model and a prompt, or a pipeline file", file=sys.stderr)
        return 2
    if args.dry_run:
        session.emitter.emit("status", message="dry-run generate")
        if args.format == "json":
            session.emitter.emit("settings", **settings)
        else:
            print(json.dumps(settings, indent=2, ensure_ascii=True))
        return 0
    result = session.generate(settings)
    return 0 if result.success else 1


def cmd_models(args: argparse.Namespace) -> int:
    session = _session(args)
    models = session.list_models(query=args.query, main_output=args.output, limit=args.limit)
    if args.format == "json":
        print(json.dumps(models, ensure_ascii=True, indent=2))
        return 0
    if not models:
        print("no models")
        return 0
    for item in models:
        model_type = item.get("model_type") or item.get("metadata", {}).get("model_type")
        name = item.get("name") or model_type
        meta = item.get("metadata") or {}
        outputs = ",".join(meta.get("main_output") or meta.get("outputs") or [])
        print(f"{model_type}\t{name}\t{outputs}")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    session = _session(args)
    data = session.schema(args.model)
    print(json.dumps(data or {}, indent=2, ensure_ascii=True))
    return 0 if data else 1


def cmd_defaults(args: argparse.Namespace) -> int:
    session = _session(args)
    data = session.defaults(args.model)
    print(json.dumps(data, indent=2, ensure_ascii=True))
    return 0


def cmd_instruct(args: argparse.Namespace) -> int:
    from wangp.instructor import instruct

    brief = args.brief
    if not brief:
        print("error: brief required", file=sys.stderr)
        return 2
    script_text = None
    if args.script:
        script_text = Path(args.script).read_text(encoding="utf-8")
    result = instruct(brief, script=script_text, notes=args.notes)
    markdown = result["markdown"]
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(markdown)
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    from wangp.script import parse_script, script_to_pipeline

    text = Path(args.path).read_text(encoding="utf-8")
    script = parse_script(text)
    payload = {"script": script, "pipeline": script_to_pipeline(script)}
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    import uvicorn

    from wangp.web import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    from wangp.config import resolve_root

    root = resolve_root(config)
    wgp = root / "wgp.py"
    if not wgp.exists():
        print(f"wgp.py not found in {root}", file=sys.stderr)
        return 1
    command = [
        sys.executable,
        str(wgp),
        "--mcp",
        "--mcp-host",
        args.host,
        "--mcp-port",
        str(args.port),
        "--mcp-transport",
        args.transport,
    ]
    extra = config.get("cli_args") or []
    if extra:
        command.extend(str(item) for item in extra)
    print(f"starting MCP at {args.host}:{args.port} ({args.transport})")
    import os

    os.execv(sys.executable, command)
    return 0


COMMANDS = {
    "init": cmd_init,
    "run": cmd_run,
    "models": cmd_models,
    "schema": cmd_schema,
    "defaults": cmd_defaults,
    "instruct": cmd_instruct,
    "parse": cmd_parse,
    "web": cmd_web,
    "serve": cmd_serve,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (WanGPNotFound, WanGPImportError, FileNotFoundError, PipelineError, InstructorError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
