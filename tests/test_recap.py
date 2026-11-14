"""Recap: what did I miss in the last few minutes."""

from test_engine import FakeProvider, make_engine  # noqa: F401  (fixture)

from shade.config import DEFAULT_HOTKEYS
from shade.engine import RECAP_SECONDS, RECAP_TASK
from shade.models import HintStarted, Status, Utterance
from shade.ui.hotkeys import ACTIONS
from shade.ui.settings_dialog import HOTKEY_LABELS


def test_recap_covers_last_minutes_not_just_context(make_engine):
    provider = FakeProvider([["- They asked about caching."]])
    engine, events, _ = make_engine(provider, now=400.0)
    engine.set_auto(False)
    engine.transcript.add(Utterance("them", "too old for a recap", 10, 12))
    # Older than context_seconds (180 s) but within the recap window.
    engine.transcript.add(Utterance("them", "We use Redis for sessions.", 400 - RECAP_SECONDS + 20, 400 - RECAP_SECONDS + 25))
    engine.transcript.add(Utterance("me", "Makes sense.", 390, 391))
    engine.recap()
    assert engine.wait_idle(5)
    assert HintStarted(1, "recap", "Recap") in events
    text = provider.user_texts[0]
    assert RECAP_TASK in text
    assert "We use Redis for sessions." in text
    assert "too old for a recap" not in text


def test_recap_is_not_kept_as_an_answer_to_follow_up(make_engine):
    provider = FakeProvider([["- recap line"], ["follow-up"]])
    engine, events, _ = make_engine(provider)
    engine.set_auto(False)
    engine.transcript.add(Utterance("them", "How do you deploy?", 90, 92))
    engine.recap()
    assert engine.wait_idle(5)
    engine.ask_now()
    assert engine.wait_idle(5)
    assert "recap line" not in provider.user_texts[1]


def test_recap_with_empty_transcript_shows_status(make_engine):
    engine, events, _ = make_engine(FakeProvider([]))
    engine.recap()
    assert events == [Status("Nothing to recap yet.")]


def test_recap_has_hotkey_and_label():
    assert "recap" in ACTIONS
    assert DEFAULT_HOTKEYS["recap"] == "<ctrl>+<alt>+r"
    assert HOTKEY_LABELS["recap"]
