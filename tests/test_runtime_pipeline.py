from wangp.events import Emitter
from wangp.pipeline import PipelineRunner
from wangp.runtime import JobResult


class StubSession:
    def __init__(self) -> None:
        self.emitter = Emitter(fmt="json")
        self.calls: list[dict] = []

    def generate(self, settings):
        self.calls.append(settings)
        path = f"/tmp/{settings['model_type']}.mp4"
        return JobResult(success=True, generated_files=[path], elapsed=0.1)


def test_pipeline_chains_outputs() -> None:
    session = StubSession()
    runner = PipelineRunner(session, emitter=session.emitter)
    pipeline = {
        "name": "chain",
        "steps": [
            {
                "id": "keyframe",
                "kind": "generate",
                "model": "t2i",
                "prompt": "${params.prompt}",
            },
            {
                "id": "motion",
                "kind": "generate",
                "model": "i2v",
                "prompt": "move",
                "settings": {"image_start": "${steps.keyframe.files.0}"},
            },
        ],
    }
    result = runner.run(pipeline, params={"prompt": "a fox"})
    assert result["success"] is True
    assert session.calls[0]["prompt"] == "a fox"
    assert session.calls[1]["image_start"] == "/tmp/t2i.mp4"
    assert result["outputs"] == ["/tmp/t2i.mp4", "/tmp/i2v.mp4"]
