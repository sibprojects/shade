"""Quick actions on the last answer: shorter, more detail, code, questions to ask."""

from test_engine import FakeProvider, make_engine  # noqa: F401  (fixture)

from shade.config import DEFAULT_HOTKEYS
from shade.engine import QUICK_ACTIONS
from shade.models import HintStarted, Status, Utterance
from shade.ui.hotkeys import ACTIONS
from shade.ui.settings_dialog import HOTKEY_LABELS


def _answer_first(engine):
    engine.transcript.add(Utterance("them", "What is dependency injection?", 80, 82))
    engine.ask_now()
    assert engine.wait_idle(5)


def test_shorter_rewrites_last_answer(make_engine):
    provider = FakeProvider([["DI passes dependencies in from outside, long answer."], ["Short one."]])
    engine, events, writer = make_engine(provider)
    _answer_first(engine)
    engine.quick_action("shorter")
    assert engine.wait_idle(5)
    assert HintStarted(2, "action", "Shorter") in events
    text = provider.user_texts[1]
    # The model sees the answer it has to shorten and the instruction.
    assert "DI passes dependencies in from outside" in text
    assert QUICK_ACTIONS["shorter"][1] in text


def test_action_answer_becomes_last_answer(make_engine):
    provider = FakeProvider([["Long answer."], ["Short one."], ["Code."]])
    engine, events, _ = make_engine(provider)
    _answer_first(engine)
    engine.quick_action("shorter")
    assert engine.wait_idle(5)
    engine.quick_action("code")
    assert engine.wait_idle(5)
    assert "A: Short one." in provider.user_texts[2]


def test_action_needing_answer_without_one_shows_status(make_engine):
    engine, events, _ = make_engine(FakeProvider([]))
    for name in ("shorter", "more", "code"):
        engine.quick_action(name)
    assert events == [Status("No answer yet.")] * 3


def test_questions_to_ask_work_without_answer(make_engine):
    provider = FakeProvider([["1. How big is the team?"]])
    engine, events, _ = make_engine(provider)
    engine.set_auto(False)
    engine.on_utterance(Utterance("them", "Do you have questions for us?", 90, 92))
    engine.quick_action("followups")
    assert engine.wait_idle(5)
    assert HintStarted(1, "action", "Questions to ask") in events
    assert "Do you have questions for us?" in provider.user_texts[0]


def test_unknown_action_is_ignored(make_engine):
    engine, events, _ = make_engine(FakeProvider([]))
    engine.quick_action("nope")
    assert events == []


def test_quick_actions_have_hotkeys_and_labels():
    for name in QUICK_ACTIONS:
        assert name in ACTIONS
        assert name in DEFAULT_HOTKEYS
        assert HOTKEY_LABELS[name]
