from fastapi.testclient import TestClient

from wangp.web import app


def test_parse_and_dry_run(monkeypatch) -> None:
    client = TestClient(app)
    text = "# Demo\n\n## Shot 1: Open\nA fox in snow.\n"
    parsed = client.post("/api/script/parse", json={"text": text})
    assert parsed.status_code == 200
    body = parsed.json()
    assert body["script"]["shots"][0]["id"] == "shot1"

    def fake_start(script, config=None, dry_run=False, runner_factory=None):
        return {"id": "abc", "status": "queued", "dry_run": dry_run, "title": script.get("title")}

    monkeypatch.setattr("wangp.web.start_script_job", fake_start)
    ran = client.post("/api/run", json={"text": text, "dry_run": True})
    assert ran.status_code == 200
    assert ran.json()["job"]["id"] == "abc"


def test_health() -> None:
    client = TestClient(app)
    data = client.get("/api/health").json()
    assert data["ok"] is True
