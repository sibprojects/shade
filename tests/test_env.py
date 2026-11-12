import os

from shade.env import load_env


def test_env_file_sets_missing_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    f = tmp_path / ".env"
    f.write_text('ANTHROPIC_API_KEY="sk-ant-test"\n# comment\n', encoding="utf-8")
    assert load_env(f) is True
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"


def test_real_environment_wins_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")
    f = tmp_path / ".env"
    f.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
    load_env(f)
    assert os.environ["OPENAI_API_KEY"] == "from-shell"


def test_missing_env_file_is_fine(tmp_path):
    assert load_env(tmp_path / ".env") is False


def test_env_file_is_ignored_by_git():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines
