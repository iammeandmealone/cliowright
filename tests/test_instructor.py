import json
from io import BytesIO

from wangp import instructor


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_instruct_parses_markdown(monkeypatch) -> None:
    monkeypatch.setenv("USER_LLM_API_KEY", "test-key")
    monkeypatch.setenv("USER_LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("USER_LLM_MODEL", "demo-model")

    payload = {
        "choices": [
            {
                "message": {
                    "content": "# Rain\n\n## Shot 1: Open\nRain on neon streets.\n"
                }
            }
        ]
    }

    def fake_urlopen(request, timeout=0):
        assert "Bearer test-key" in request.headers["Authorization"]
        return FakeResponse(payload)

    monkeypatch.setattr(instructor.urllib.request, "urlopen", fake_urlopen)
    result = instructor.instruct("make a rainy street video")
    assert result["model"] == "demo-model"
    assert result["script"]["title"] == "Rain"
    assert result["script"]["shots"][0]["prompt"].startswith("Rain on neon")


def test_configured_false_without_key(monkeypatch) -> None:
    monkeypatch.delenv("USER_LLM_API_KEY", raising=False)
    monkeypatch.chdir("/tmp")
    assert instructor.configured() is False
