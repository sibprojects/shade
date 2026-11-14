"""Transcript like live captions: one speaker's phrases join one line until the other side speaks."""

from datetime import datetime

from shade.models import Utterance, UtteranceAdded
from shade.notes import has_speech
from shade.session import SessionWriter
from shade.transcript import format_lines
from shade.ui.hint_view import HintView

HELLO = Utterance("them", "hello!", 1, 2)
HOW = Utterance("them", "how are you?", 2, 3)
FINE = Utterance("me", "Fine, thanks.", 4, 5)
AND_YOU = Utterance("me", "And you?", 5, 6)
NOTE1 = Utterance("note", "Be brief.", 6, 6)
NOTE2 = Utterance("note", "Use Go.", 7, 7)


def test_format_lines_joins_one_speakers_phrases():
    assert format_lines([HELLO, HOW]) == "[00:01] Them: hello! how are you?"
    assert format_lines([HELLO, HOW, FINE, AND_YOU]) == (
        "[00:01] Them: hello! how are you?\n[00:04] Me: Fine, thanks. And you?"
    )


def test_notes_are_never_joined():
    assert format_lines([NOTE1, NOTE2]) == "[00:06] Note: Be brief.\n[00:07] Note: Use Go."


def test_view_joins_lines_too(qtbot):
    for compact in (False, True):
        v = HintView(compact=compact, transcript_lines=3 if compact else None)
        qtbot.addWidget(v)
        for u in (HELLO, HOW, FINE, AND_YOU, NOTE1, NOTE2, Utterance("them", "Great.", 8, 9)):
            v.handle(UtteranceAdded(u))
        assert v.transcript_text() == (
            "[00:01] Them: hello! how are you?\n"
            "[00:04] Me: Fine, thanks. And you?\n"
            "[00:06] Note: Be brief.\n"
            "[00:07] Note: Use Go.\n"
            "[00:08] Them: Great."
        )


def test_overlay_keeps_more_than_three_turns(qtbot):
    v = HintView(compact=True, transcript_lines=3)
    qtbot.addWidget(v)
    for i in range(10):
        v.handle(UtteranceAdded(Utterance("them" if i % 2 else "me", f"turn {i}", i, i + 1)))
    assert "turn 0" in v.transcript_text()  # the strip can be dragged taller, so keep history


def test_session_file_joins_lines_and_stays_append_only(tmp_path):
    w = SessionWriter(tmp_path, "T", datetime(2026, 11, 14, 10, 0))
    for u in (HELLO, HOW, FINE):
        w.write_utterance(u)
    path = w.dir / "transcript.md"
    # Written as it goes (crash-safe), already joined.
    assert path.read_text(encoding="utf-8").endswith("[00:01] Them: hello! how are you?\n[00:04] Me: Fine, thanks.")
    w.write_utterance(AND_YOU)
    w.close()
    text = path.read_text(encoding="utf-8")
    assert text.endswith("[00:01] Them: hello! how are you?\n[00:04] Me: Fine, thanks. And you?\n")
    assert has_speech(w.dir)
