from pathlib import Path

from wangp.cli import main


def test_help() -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--path", str(tmp_path / "wangp.json")]) == 0
    assert (tmp_path / "wangp.json").exists()
    assert main(["init", "--path", str(tmp_path / "wangp.json")]) == 1


def test_run_pipeline_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = tmp_path / "job.yaml"
    pipeline.write_text(
        "name: demo\nsteps:\n  - id: clip\n    kind: generate\n    model: t2v\n    prompt: ${params.prompt}\n",
        encoding="utf-8",
    )
    code = main(
        [
            "--format",
            "json",
            "run",
            str(pipeline),
            "--param",
            "prompt=a fox in snow",
            "--dry-run",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "clip" in out
    assert "generate" in out


def test_run_requires_model(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["run", "just a prompt"])
    assert code == 2
