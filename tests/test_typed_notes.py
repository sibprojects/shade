"""Typed notes to the AI during the call: Enter asks now, Ctrl+Enter only adds to the context."""

from PySide6.QtCore import Qt
from test_engine import FakeDetector, FakeProvider, make_engine  # noqa: F401  (fixture)

from shade.models import HintStarted, Utterance, UtteranceAdded
from shade.prompt import ANSWER_RULES
from shade.transcript import format_lines
from shade.ui.hint_view import HintView


def test_note_asks_now_and_lands_in_transcript(make_engine):
    provider = FakeProvider([["Sure, in Go:"]])
    engine, events, writer = make_engine(provider)
    engine.set_auto(False)
    engine.transcript.add(Utterance("them", "Write a function that reverses a list.", 90, 92))
    engine.add_note("They want it in Go, not PHP.", ask=True)
    assert engine.wait_idle(5)
    assert UtteranceAdded(Utterance("note", "They want it in Go, not PHP.", 100.0, 100.0)) in events
    assert HintStarted(1, "typed", "They want it in Go, not PHP.") in events
    text = provider.user_texts[0]
    assert "Note: They want it in Go, not PHP." in text  # in the conversation
    assert "Write a function that reverses a list." in text
    assert "Note: They want it in Go, not PHP." in (writer.dir / "transcript.md").read_text(encoding="utf-8")


def test_note_without_asking_goes_along_with_the_next_answer(make_engine):
    provider = FakeProvider([["answer"]])
    engine, events, _ = make_engine(provider)
    engine.set_auto(False)
    engine.transcript.add(Utterance("them", "How do you scale reads?", 90, 92))
    engine.add_note("The interviewer is the CTO.", ask=False)
    assert not [e for e in events if isinstance(e, HintStarted)]
    engine.ask_now()
    assert engine.wait_idle(5)
    assert HintStarted(1, "hotkey", "How do you scale reads?") in events  # the note doesn't hide the question
    assert "Note: The interviewer is the CTO." in provider.user_texts[0]


def test_note_does_not_trigger_question_detection(make_engine):
    detector = FakeDetector()
    engine, events, _ = make_engine(FakeProvider([]), detector=detector)
    engine.add_note("What a strange question?", ask=False)
    assert engine.wait_idle(5)
    assert detector.calls == 0


def test_empty_note_is_ignored(make_engine):
    engine, events, _ = make_engine(FakeProvider([]))
    engine.add_note("   ", ask=True)
    assert events == []


def test_notes_are_labelled_and_explained_to_the_model():
    assert format_lines([Utterance("note", "Use Go.", 61, 61)]) == "[01:01] Note: Use Go."
    assert "Note" in ANSWER_RULES


def _view(qtbot, compact):
    v = HintView(compact=compact, transcript_lines=3 if compact else None)
    qtbot.addWidget(v)
    sent = []
    v.note_submitted.connect(lambda text, ask: sent.append((text, ask)))
    return v, sent


def test_note_box_enter_asks_ctrl_enter_only_adds(qtbot):
    for compact in (False, True):
        v, sent = _view(qtbot, compact)
        qtbot.keyClicks(v.note, "Answer in Go")
        qtbot.keyClick(v.note, Qt.Key.Key_Return)
        assert sent == [("Answer in Go", True)]
        assert v.note.text() == ""
        qtbot.keyClicks(v.note, "CTO is here")
        qtbot.keyClick(v.note, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        assert sent[-1] == ("CTO is here", False)
        qtbot.keyClick(v.note, Qt.Key.Key_Return)  # empty: nothing sent
        assert len(sent) == 2
