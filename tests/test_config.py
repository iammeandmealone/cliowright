from pathlib import Path

from wangp.config import DEFAULT_CONFIG, load_config, merge, wan_cli_args, write_example


def test_merge_nested() -> None:
    merged = merge({"a": 1, "b": {"c": 2, "d": 3}}, {"b": {"c": 9}, "e": 4})
    assert merged["a"] == 1
    assert merged["b"]["c"] == 9
    assert merged["b"]["d"] == 3
    assert merged["e"] == 4


def test_load_project_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WANGP_CONFIG", raising=False)
    monkeypatch.delenv("WANGP_ROOT", raising=False)
    (tmp_path / "wangp.json").write_text(
        '{"profile": 5, "defaults": {"model": "t2v"}}',
        encoding="utf-8",
    )
    config = load_config()
    assert config["profile"] == 5
    assert config["defaults"]["model"] == "t2v"
    assert config["attention"] == DEFAULT_CONFIG["attention"]


def test_write_example(tmp_path: Path) -> None:
    path = tmp_path / "wangp.json"
    write_example(path)
    assert path.exists()
    loaded = load_config(path)
    assert loaded["$schema"]


def test_wan_cli_args() -> None:
    args = wan_cli_args({"profile": 4, "attention": "sage2", "offline": True, "cli_args": ["--fp16"]})
    assert args == ["--profile", "4", "--attention", "sage2", "--offline", "--fp16"]
