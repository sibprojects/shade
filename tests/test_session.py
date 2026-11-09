from datetime import datetime

from shade.models import HintRequest, Usage, Utterance
from shade.session import SessionWriter

STARTED = datetime(2026, 11, 9, 14, 5)


def _writer(tmp_path):
    return SessionWriter(tmp_path, "Job Interview", STARTED)


def test_creates_dir_and_headers(tmp_path):
    w = _writer(tmp_path)
    assert w.dir == tmp_path / "2026-11-09_14-05_job-interview"
    assert (w.dir / "transcript.md").read_text(encoding="utf-8").startswith(
        "# Transcript — Job Interview — 2026-11-09 14:05\n\n"
    )
    assert (w.dir / "hints.md").read_text(encoding="utf-8").startswith(
        "# Hints — Job Interview — 2026-11-09 14:05\n\n"
    )
    w.close()


def test_utterance_appended_and_flushed(tmp_path):
    w = _writer(tmp_path)
    w.write_utterance(Utterance("them", "Why Python?", 65.0, 66.0))
    assert "[01:05] Them: Why Python?\n" in (w.dir / "transcript.md").read_text(encoding="utf-8")
    w.close()


def test_hint_with_image_saves_png_and_link(tmp_path):
    w = _writer(tmp_path)
    req = HintRequest(3, "screenshot", "Fix this", [Utterance("them", "x", 125.0, 126.0)], b"PNGDATA")
    w.write_hint(req, "Use a set.", "claude-opus-5-5", Usage(100, 20), 0.0008, 0.0123)
    text = (w.dir / "hints.md").read_text(encoding="utf-8")
    assert "## [02:06] #3 (screenshot) — claude-opus-5-5\n" in text
    assert "**Q:** Fix this\n" in text
    assert "![screenshot](hint-3.png)\n" in text
    assert "Use a set.\n" in text
    assert "_tokens in/out: 100/20 · cost: $0.0008 · session total: $0.0123_" in text
    assert (w.dir / "hint-3.png").read_bytes() == b"PNGDATA"
    w.close()


def test_error_written(tmp_path):
    w = _writer(tmp_path)
    req = HintRequest(1, "hotkey", "Q?", [])
    w.write_error(req, "Claude: cannot connect.")
    text = (w.dir / "hints.md").read_text(encoding="utf-8")
    assert "#1 (hotkey)" in text
    assert "**Error:** Claude: cannot connect." in text
    w.close()


def test_transcript_only_appends(tmp_path):
    w = _writer(tmp_path)
    path = w.dir / "transcript.md"
    previous = path.read_text(encoding="utf-8")
    for i in range(3):
        w.write_utterance(Utterance("me", f"line {i}", i, i + 1))
        current = path.read_text(encoding="utf-8")
        assert len(current) > len(previous)
        assert current.startswith(previous)
        previous = current
    w.close()
