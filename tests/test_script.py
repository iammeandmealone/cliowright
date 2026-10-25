from wangp.script import parse_script, script_to_pipeline


SAMPLE = """# Night Fox

A three-shot walk.

model_type: t2v
resolution: 832x480
video_length: 5s

## Shot 1: Open
Wide night street. A fox steps in.

## Shot 2: Look
continue: previous
The fox looks up at a sign.

## Shot 3: Leave
continue: previous
The fox walks into the rain.
"""


def test_parse_markdown_shots() -> None:
    script = parse_script(SAMPLE)
    assert script["title"] == "Night Fox"
    assert script["defaults"]["model_type"] == "t2v"
    assert script["defaults"]["resolution"] == "832x480"
    assert len(script["shots"]) == 3
    assert "fox steps" in script["shots"][0]["prompt"]
    assert script["shots"][1]["continue"] == "previous"


def test_script_to_pipeline_continues() -> None:
    pipeline = script_to_pipeline(parse_script(SAMPLE))
    assert pipeline["name"] == "Night Fox"
    assert len(pipeline["steps"]) == 3
    motion = pipeline["steps"][1]
    assert motion["settings"]["video_source"] == "${steps.shot1.files.0}"
    assert "V" in motion["settings"]["image_prompt_type"]


def test_parse_yaml() -> None:
    script = parse_script(
        "title: Demo\nshots:\n  - prompt: a cat\n    model: t2v\n    steps: 8\n"
    )
    assert script["shots"][0]["prompt"] == "a cat"
    assert script["shots"][0]["model_type"] == "t2v"
    assert script["shots"][0]["num_inference_steps"] == 8
