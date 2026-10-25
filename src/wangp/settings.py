from __future__ import annotations

from typing import Any

SETTING_FIELDS: list[dict[str, Any]] = [
    {
        "key": "model_type",
        "label": "Model",
        "kind": "string",
        "aliases": ["model"],
        "help": "WanGP model_type id from wangp models. Example: t2v, i2v, or a real id like ltx2_22B_distilled.",
    },
    {
        "key": "prompt",
        "label": "Prompt",
        "kind": "text",
        "aliases": ["text"],
        "help": "What happens in this shot. One shot, one prompt.",
    },
    {
        "key": "negative_prompt",
        "label": "Negative prompt",
        "kind": "text",
        "aliases": ["negative"],
        "help": "What to avoid. Optional.",
    },
    {
        "key": "resolution",
        "label": "Resolution",
        "kind": "string",
        "aliases": ["size", "wxh"],
        "help": "Width x height, for example 832x480 or 1280x704. Must match the model grid.",
    },
    {
        "key": "video_length",
        "label": "Length",
        "kind": "string",
        "aliases": ["duration", "length", "frames"],
        "help": "Shot length as frames or seconds, for example 81 or 5s. WanGP snaps to a valid frame count.",
    },
    {
        "key": "num_inference_steps",
        "label": "Steps",
        "kind": "int",
        "aliases": ["steps"],
        "help": "Denoising steps. Distilled models often use 4-8. Base models use more.",
    },
    {
        "key": "seed",
        "label": "Seed",
        "kind": "int",
        "aliases": [],
        "help": "Integer seed. -1 means random. Reuse a seed to keep look consistent across shots.",
    },
    {
        "key": "force_fps",
        "label": "FPS",
        "kind": "int",
        "aliases": ["fps"],
        "help": "Output frames per second when the model allows it.",
    },
    {
        "key": "image_start",
        "label": "Start image",
        "kind": "path",
        "aliases": ["start", "first_frame"],
        "help": "Opening frame. Sets image_prompt_type S.",
    },
    {
        "key": "image_end",
        "label": "End image",
        "kind": "path",
        "aliases": ["end", "last_frame"],
        "help": "Closing frame / identity anchor. Sets image_prompt_type E.",
    },
    {
        "key": "image_refs",
        "label": "Reference images",
        "kind": "list",
        "aliases": ["refs", "reference"],
        "help": "Subject or style references. Needs a video_prompt_type that contains I.",
    },
    {
        "key": "image_prompt_type",
        "label": "Image flags",
        "kind": "string",
        "aliases": ["image_mode"],
        "help": "S start, E end, V continue from video_source. Combine as SE or SV.",
    },
    {
        "key": "video_source",
        "label": "Continue from",
        "kind": "path",
        "aliases": ["source"],
        "help": "Previous clip to extend. Sets image_prompt_type V.",
    },
    {
        "key": "video_prompt_type",
        "label": "Video flags",
        "kind": "string",
        "aliases": [],
        "help": "Model-specific control flags. I reference, K background, F injected frames, V control video.",
    },
    {
        "key": "sliding_window_size",
        "label": "Window size",
        "kind": "int",
        "aliases": ["window"],
        "help": "Frames per sliding window for long shots. Stay at or below the model frames_maximum.",
    },
    {
        "key": "activated_loras",
        "label": "LoRAs",
        "kind": "list",
        "aliases": ["loras"],
        "help": "Exact LoRA ids from wangp / WanGP. Pair with loras_multipliers.",
    },
    {
        "key": "loras_multipliers",
        "label": "LoRA strengths",
        "kind": "string",
        "aliases": ["lora_weights"],
        "help": "Strengths matching activated_loras, for example 1;0.6.",
    },
]

ALIAS_TO_KEY = {}
for _field in SETTING_FIELDS:
    ALIAS_TO_KEY[_field["key"]] = _field["key"]
    for _alias in _field["aliases"]:
        ALIAS_TO_KEY[_alias] = _field["key"]


def catalog() -> list[dict[str, Any]]:
    return list(SETTING_FIELDS)


def normalize_settings(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        canon = ALIAS_TO_KEY.get(str(key).strip().lower(), key)
        if value is None or value == "":
            continue
        out[canon] = value
    if out.get("image_start") and "S" not in str(out.get("image_prompt_type") or ""):
        out["image_prompt_type"] = str(out.get("image_prompt_type") or "") + "S"
    if out.get("image_end") and "E" not in str(out.get("image_prompt_type") or ""):
        out["image_prompt_type"] = str(out.get("image_prompt_type") or "") + "E"
    if out.get("video_source") and "V" not in str(out.get("image_prompt_type") or ""):
        out["image_prompt_type"] = str(out.get("image_prompt_type") or "") + "V"
    if "model" in out and "model_type" not in out:
        out["model_type"] = out.pop("model")
    return out


def describe(key: str) -> dict[str, Any] | None:
    canon = ALIAS_TO_KEY.get(key.strip().lower(), key)
    for field in SETTING_FIELDS:
        if field["key"] == canon:
            return field
    return None
