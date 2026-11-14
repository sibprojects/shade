"""Call notes after a session: summary, questions and how I answered, tasks, follow-up email."""

import threading
from datetime import datetime

import pytest

from shade.config import Settings, load_settings, save_settings
from shade.llm.base import ProviderError
from shade.models import HintRequest, Usage, Utterance
from shade.notes import (
    NOTES_FILE,
    NOTES_RULES,
    build_notes_request,
    has_speech,
    latest_session,
    make_notes,
    start_notes,
)
from shade.session import SessionWriter


class Fake:
    model = "fake"
    supports_images = True

    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.last_usage = Usage()
        self.calls = []
        self.closed = False

    def stream_answer(self, system, user_text, image_png, cancel):
        self.calls.append((system, user_text))
        if self.error:
            raise self.error
        yield from self.chunks

    def close(self):
        self.closed = True


@pytest.fixture
def session_dir(tmp_path):
    w = SessionWriter(tmp_path, "PHP interview", datetime(2026, 11, 14, 15, 0))
    w.write_utterance(Utterance("them", "How do you handle retries in queues?", 60, 63))
    w.write_utterance(Utterance("me", "We use exponential backoff and a dead letter queue.", 64, 70))
    req = HintRequest(1, "auto", "How do you handle retries in queues?", [Utterance("them", "x", 60, 63)])
    w.write_hint(req, "Exponential backoff, idempotent consumers, DLQ.", "fake", Usage(), 0.0, 0.0)
    w.close()
    return w.dir


def test_request_has_transcript_and_hints(session_dir):
    text = build_notes_request(session_dir)
    assert "How do you handle retries in queues?" in text
    assert "We use exponential backoff" in text
    assert "idempotent consumers" in text


def test_rules_ask_for_the_sections():
    for section in ("## Summary", "## Questions", "## To do", "## Follow-up email"):
        assert section in NOTES_RULES


def test_make_notes_writes_notes_file(session_dir):
    p = Fake(["# Call notes\n\n## Summary\n", "- Queues."])
    path = make_notes(p, session_dir, threading.Event())
    assert path == session_dir / NOTES_FILE
    assert path.read_text(encoding="utf-8") == "# Call notes\n\n## Summary\n- Queues.\n"
    assert p.calls[0][0] == NOTES_RULES


def test_session_without_speech_has_nothing_to_summarize(tmp_path):
    w = SessionWriter(tmp_path, "Empty", datetime(2026, 11, 14, 15, 0))
    w.close()
    assert not has_speech(w.dir)
    with pytest.raises(ValueError, match="Nothing to summarize"):
        make_notes(Fake(["x"]), w.dir, threading.Event())


def test_has_speech(session_dir):
    assert has_speech(session_dir)


def test_long_transcript_keeps_the_end(tmp_path):
    w = SessionWriter(tmp_path, "Long", datetime(2026, 11, 14, 15, 0))
    for i in range(6000):
        w.write_utterance(Utterance("them", f"line number {i} with some words", i, i + 1))
    w.close()
    text = build_notes_request(w.dir)
    assert "line number 5999" in text
    assert len(text) < 160_000


def test_latest_session(tmp_path):
    assert latest_session(tmp_path) is None
    for name in ("2026-11-13_10-00_a", "2026-11-14_09-00_b", "2026-11-13_23-00_c"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "transcript.md").write_text("x")
    (tmp_path / "2026-11-15_00-00_empty").mkdir()  # not a session: no transcript
    assert latest_session(tmp_path) == tmp_path / "2026-11-14_09-00_b"


def test_start_notes_reports_done_and_closes_provider(session_dir):
    p = Fake(["# Notes\n"])
    done, failed = [], []
    t = start_notes(lambda: p, session_dir, done.append, failed.append)
    t.join(5)
    assert done == [session_dir / NOTES_FILE] and failed == []
    assert p.closed


def test_start_notes_reports_errors(session_dir):
    done, failed = [], []
    t = start_notes(lambda: Fake([], error=ProviderError("Claude Code: usage limit.")), session_dir, done.append, failed.append)
    t.join(5)
    assert done == []
    assert failed == ["Call notes failed: Claude Code: usage limit."]


def test_auto_notes_setting(tmp_path, qtbot):
    from shade.ui.settings_dialog import SettingsDialog

    assert Settings().auto_notes is True
    path = tmp_path / "s.toml"
    save_settings(Settings(auto_notes=False), path)
    assert load_settings(path).auto_notes is False
    d = SettingsDialog(Settings(), {}, start_meter=False)
    qtbot.addWidget(d)
    d.auto_notes.setChecked(False)
    assert d.result_settings().auto_notes is False
