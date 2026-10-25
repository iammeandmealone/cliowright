from wangp.pipeline import PipelineError, interpolate, load_pipeline, merge_settings
from pathlib import Path

import pytest


def test_interpolate_nested() -> None:
    context = {
        "params": {"prompt": "a cat"},
        "steps": {"keyframe": {"files": ["/tmp/a.png"]}},
    }
    assert interpolate("${params.prompt}", context) == "a cat"
    assert interpolate("${steps.keyframe.files.0}", context) == "/tmp/a.png"
    assert interpolate("see ${params.prompt} now", context) == "see a cat now"


def test_interpolate_unknown() -> None:
    with pytest.raises(PipelineError):
        interpolate("${missing.x}", {})


def test_load_pipeline(tmp_path: Path) -> None:
    path = tmp_path / "pipe.yaml"
    path.write_text(
        "name: demo\nsteps:\n  - id: a\n    kind: generate\n    model: t2v\n    prompt: hi\n",
        encoding="utf-8",
    )
    data = load_pipeline(path)
    assert data["name"] == "demo"
    assert len(data["steps"]) == 1


def test_merge_settings() -> None:
    merged = merge_settings({"a": 1, "b": {"x": 1}}, {"b": {"y": 2}, "c": 3})
    assert merged == {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}
