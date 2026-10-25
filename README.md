# wangp

Headless CLI pipeline for [WanGP](https://github.com/deepbeepmeep/WanGP). No Gradio. No notebooks.

MonkeyCode drives OpenCode with `opencode run`. This package does the same for WanGP:

```bash
wangp run -m t2v "a fox walking through snow"
wangp run examples/image_then_video.yaml --param prompt="a fox" --param motion="the fox turns"
```

WanGP stays the generator. `wangp` is the non-interactive front door: config file, one-shot generate, YAML pipelines, JSON events, MCP serve.

## Install

WanGP itself is not bundled. Point `wangp` at an existing WanGP / Wan2GP checkout.

```bash
pip install -e .
```

```bash
wangp init
```

Edit `wangp.json`:

```json
{
  "root": "/path/to/Wan2GP",
  "output_dir": "outputs",
  "profile": 4,
  "attention": "sdpa"
}
```

Or set `WANGP_ROOT`. Config is merged from `WANGP_CONFIG`, `./wangp.json`, and `~/.config/wangp/wangp.json`.

## Commands

| Command | Purpose |
|---|---|
| `wangp init` | Write a starter `wangp.json` |
| `wangp run PROMPT` | One-shot generate (needs `--model`) |
| `wangp run job.yaml` | Multi-step pipeline |
| `wangp run queue.zip` | Headless saved WanGP queue |
| `wangp parse script.md` | Parse a video script into shots and settings |
| `wangp instruct "brief"` | Draft a script with the instructor agent |
| `wangp web` | Script / settings / instructor UI |
| `wangp models [query]` | List models |
| `wangp schema MODEL` | Compact model schema |
| `wangp defaults MODEL` | Default generation settings |
| `wangp serve` | Start WanGP MCP (`python wgp.py --mcp`) |

Same shape as OpenCode: `run` is non-interactive, `serve` is the headless server, `--format json` emits one event per line.

```bash
# one shot
wangp run -m t2v --length 5s --steps 8 "cinematic rain on neon streets"

# image to video
wangp run -m i2v --image start.png "the camera dollies in"

# exported WanGP settings
wangp run --settings my_settings.json

# overnight queue (create the zip in the WanGP UI once, then leave the UI)
wangp run overnight.zip --output-dir ./renders

# validate a pipeline without touching the GPU
wangp run examples/text_to_video.yaml --param prompt="test" --dry-run
```

JSON events:

```bash
wangp run -m t2v "a cat" --format json
```

```json
{"type":"progress","step":4,"total":8,"phase":"Denoising"}
{"type":"file","path":"outputs/clip.mp4"}
{"type":"done","success":true,"elapsed":"1m 12s"}
```

## Pipeline YAML

```yaml
name: image-then-video
defaults:
  seed: -1
steps:
  - id: keyframe
    kind: generate
    model: t2i
    prompt: ${params.prompt}
    settings:
      resolution: 1024x1024
  - id: motion
    kind: generate
    model: i2v
    prompt: ${params.motion}
    settings:
      image_start: ${steps.keyframe.files.0}
      image_prompt_type: S
      video_length: 5s
```

```bash
wangp run examples/image_then_video.yaml \
  --param prompt="a red fox in snow, still, cinematic" \
  --param motion="the fox turns its head"
```

Step kinds: `generate`, `settings` (exported JSON), `queue` (saved `.zip`). `${params.*}` and `${steps.<id>.files.0}` are interpolated before each step.

Use real `model_type` values from `wangp models`. `t2v` / `t2i` / `i2v` in the examples are placeholders.

## Video scripts

Write shots in Markdown. Shared settings go once at the top. Later shots can `continue: previous` to extend the last clip.

```markdown
# Night Fox

model_type: t2v
resolution: 832x480
video_length: 5s
num_inference_steps: 8

## Shot 1: Open
Wide night street, rain, neon. A fox steps into frame.

## Shot 2: Look
continue: previous
The fox looks up at a flickering sign.
```

```bash
wangp parse examples/night_fox.md
wangp run examples/night_fox.md --dry-run
```

Setting keys: `model_type`, `resolution`, `video_length`, `num_inference_steps`, `seed`, `force_fps`, `image_start`, `image_end`, `image_refs`, `image_prompt_type`, `video_source`, `negative_prompt`, LoRAs. Aliases like `model`, `steps`, `length` are accepted.

## Instructor agent

Uses **your** LLM key, not Deepy and not this environment. Copy `.env.example` to `.env` and fill:

```env
USER_LLM_API_KEY=your-api-key-here
USER_LLM_BASE_URL=https://api.deepseek.com/v1
USER_LLM_MODEL=deepseek-chat
```

```bash
wangp instruct "3-shot night street, a fox in the rain, 5s each"
wangp web --port 8000
```

The UI drafts or revises a script, shows shot settings, and queues a pipeline run.

## vs Gradio / notebooks / Deepy

| | Gradio / notebook | Deepy | wangp |
|---|---|---|---|
| UI | required | chat | script + settings |
| Batch | Save Queue zip | chat turns | Markdown / YAML + `run` |
| Instructor | Deepy VRAM | Deepy Prime | your `USER_LLM_*` key |
| Events | browser | terminal chat | text or JSONL |
| MCP | `wgp.py --mcp` | Deepy Prime | `wangp serve` |

`wangp` talks to WanGP through `shared.api` (`init` / `submit_task`). Model weights, VRAM profiles, and kernels stay in WanGP.

## MonkeyCode-style usage

```bash
# attach-style: keep MCP warm, then generate
wangp serve --port 8000

# one-shot jobs in scripts / CI
wangp run -m t2v --format json "..." >> events.jsonl
```

Remote LLMs (OpenCode, Codex, Claude Code) stay inside WanGP Deepy Prime. This CLI does not start those engines; it only drives generation.
