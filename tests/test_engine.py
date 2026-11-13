import threading
import time
from datetime import datetime

import pytest

from shade.cost import CostMeter
from shade.engine import Engine
from shade.llm.base import ProviderError
from shade.models import (
    HintDelta,
    HintDone,
    HintError,
    HintStarted,
    Status,
    Usage,
    Utterance,
    UtteranceAdded,
)
from shade.session import SessionWriter
from shade.transcript import Transcript


class FakeProvider:
    """Each call to stream_answer consumes the next script entry.

    A script entry is a list of chunks; a chunk may be a threading.Event, which
    makes the stream wait for it (to simulate a slow stream), or an Exception,
    which is raised.
    """

    model = "fake-model"
    detector_model = "fake-model"

    def __init__(self, scripts, supports_images=True):
        self.scripts = list(scripts)
        self.supports_images = supports_images
        self.last_usage = Usage()
        self.user_texts = []

    def stream_answer(self, system, user_text, image_png, cancel):
        self.user_texts.append(user_text)
        script = self.scripts.pop(0)
        for item in script:
            if isinstance(item, threading.Event):
                item.wait(5)
                continue
            if isinstance(item, Exception):
                raise item
            yield item
            if cancel.is_set():
                return
        self.last_usage = Usage(100, 10)

    def detect(self, system, user_text):
        return "NONE"


class FakeDetector:
    def __init__(self, answer="How do you test it?"):
        self.answer = answer
        self.calls = 0

    def check(self, latest, recent):
        self.calls += 1
        return self.answer if latest.source == "them" else None


@pytest.fixture
def make_engine(tmp_path):
    engines = []

    def _make(provider, detector=None, now=100.0):
        events = []
        writer = SessionWriter(tmp_path, "Test", datetime(2026, 11, 9, 10, 0))
        engine = Engine(
            provider=provider,
            detector=detector or FakeDetector(),
            transcript=Transcript(),
            writer=writer,
            cost=CostMeter({"fake-model": [1.0, 2.0]}),
            profile_text="I am a tester.",
            context_seconds=180,
            on_event=events.append,
            clock=lambda: now,
        )
        engines.append(engine)
        return engine, events, writer

    yield _make
    for e in engines:
        e.stop()


def wait_for(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def hints_text(writer):
    return (writer.dir / "hints.md").read_text(encoding="utf-8")


def test_auto_flow_emits_started_deltas_done(make_engine):
    engine, events, writer = make_engine(FakeProvider([["Hel", "lo"]]))
    engine.on_utterance(Utterance("them", "How do you test it?", 90, 92))
    assert engine.wait_idle(5)
    kinds = [type(e) for e in events]
    assert kinds == [UtteranceAdded, HintStarted, HintDelta, HintDelta, HintDone]
    assert events[1] == HintStarted(1, "auto", "How do you test it?")
    done = events[-1]
    assert done.model == "fake-model"
    assert done.cost == pytest.approx((100 * 1.0 + 10 * 2.0) / 1e6)
    assert "Hello" in hints_text(writer)


def test_provider_error_becomes_hint_error_and_transcription_continues(make_engine):
    engine, events, writer = make_engine(FakeProvider([[ProviderError("Claude: cannot connect.")]]))
    engine.on_utterance(Utterance("them", "How do you test it?", 90, 92))
    assert engine.wait_idle(5)
    assert HintError(1, "Claude: cannot connect.") in events
    assert "**Error:** Claude: cannot connect." in hints_text(writer)
    engine.on_utterance(Utterance("me", "Still here", 93, 94))
    assert isinstance(events[-1], UtteranceAdded)
    assert "Me: Still here" in (writer.dir / "transcript.md").read_text(encoding="utf-8")


def test_hotkey_cancels_running_auto(make_engine):
    gate = threading.Event()
    provider = FakeProvider([["first", gate, "never"], ["second"]])
    engine, events, writer = make_engine(provider)
    engine.on_utterance(Utterance("them", "How do you test it?", 90, 92))
    assert wait_for(lambda: HintDelta(1, "first") in events)
    engine.ask_now()
    gate.set()
    assert engine.wait_idle(5)
    assert HintStarted(2, "hotkey", "How do you test it?") in events
    assert HintDelta(1, "never") not in events
    text = hints_text(writer)
    assert "first _(cancelled)_" in text
    assert "second" in text


def test_auto_dropped_while_hotkey_running(make_engine):
    gate = threading.Event()
    provider = FakeProvider([["answer", gate, " done"]])
    engine, events, writer = make_engine(provider)
    engine.transcript.add(Utterance("them", "What is TDD?", 80, 82))
    engine.ask_now()
    assert wait_for(lambda: HintDelta(1, "answer") in events)
    engine.on_utterance(Utterance("them", "And how do you test it?", 90, 92))
    time.sleep(0.1)
    gate.set()
    assert engine.wait_idle(5)
    started = [e for e in events if isinstance(e, HintStarted)]
    assert started == [HintStarted(1, "hotkey", "What is TDD?")]
    assert HintDelta(1, " done") in events


def test_screenshot_without_vision_message(make_engine):
    engine, events, _ = make_engine(FakeProvider([], supports_images=False))
    engine.ask_with_image(b"png")
    assert engine.wait_idle(5)
    assert [e for e in events if isinstance(e, HintError)] == [
        HintError(1, "Selected local model does not support images.")
    ]


def test_screenshot_starts_hint_with_image(make_engine):
    engine, events, writer = make_engine(FakeProvider([["Use a set."]]))
    engine.ask_with_image(b"PNGDATA")
    assert engine.wait_idle(5)
    assert HintStarted(1, "screenshot", "") in events
    assert (writer.dir / "hint-1.png").read_bytes() == b"PNGDATA"


def test_ask_now_without_question_status(make_engine):
    engine, events, _ = make_engine(FakeProvider([]))
    engine.ask_now()
    assert events == [Status("No question yet.")]


def test_context_limited_to_context_seconds(make_engine):
    provider = FakeProvider([["ok"]])
    engine, events, _ = make_engine(provider, now=400.0)
    engine.transcript.add(Utterance("them", "ancient words", 10, 12))
    engine.on_utterance(Utterance("them", "How do you test it?", 390, 392))
    assert engine.wait_idle(5)
    assert "ancient words" not in provider.user_texts[0]
    assert "How do you test it?" in provider.user_texts[0]


def test_auto_disabled_skips_detector(make_engine):
    detector = FakeDetector()
    engine, events, _ = make_engine(FakeProvider([]), detector=detector)
    engine.set_auto(False)
    engine.on_utterance(Utterance("them", "How do you test it?", 90, 92))
    assert engine.wait_idle(5)
    assert detector.calls == 0
    assert not any(isinstance(e, HintStarted) for e in events)


def test_internal_error_becomes_status(make_engine):
    provider = FakeProvider([[RuntimeError("boom")]])
    engine, events, _ = make_engine(provider)
    engine.on_utterance(Utterance("them", "How do you test it?", 90, 92))
    assert engine.wait_idle(5)
    assert Status("Internal error: boom") in events


def test_rule_detector_starts_hints_without_asking_the_model(make_engine):
    from shade.detect import RuleDetector

    class NoDetectProvider(FakeProvider):
        def detect(self, system, user_text):
            raise AssertionError("detection must not call the model")

    engine, events, writer = make_engine(NoDetectProvider([["Use", " a cache."]]), detector=RuleDetector())
    engine.on_utterance(Utterance("them", "Our stack is Go and React.", 85, 88))
    engine.on_utterance(Utterance("them", "How would you scale the reads?", 90, 92))
    assert engine.wait_idle(5)
    started = [e for e in events if isinstance(e, HintStarted)]
    assert [e.question for e in started] == ["How would you scale the reads?"]


def test_follow_up_questions_see_the_earlier_answers(make_engine):
    provider = FakeProvider([["Use Redis with a TTL."], ["Write-through."]])
    engine, events, writer = make_engine(provider)
    engine.on_utterance(Utterance("them", "How would you cache it?", 80, 82))
    engine.ask_now()
    assert engine.wait_idle(5)
    engine.on_utterance(Utterance("them", "And what about writes?", 90, 92))
    engine.ask_now()
    assert engine.wait_idle(5)
    second = provider.user_texts[1]
    assert "Use Redis with a TTL." in second and "How would you cache it?" in second
    assert second.index("Use Redis") < second.index("Answer this now")


def test_only_the_last_three_answers_are_sent(make_engine):
    provider = FakeProvider([[f"Answer {i}."] for i in range(5)])
    engine, events, writer = make_engine(provider)
    for i in range(5):
        engine.on_utterance(Utterance("them", f"Question {i}?", 10 * i, 10 * i + 2))
        engine.ask_now()
        assert engine.wait_idle(5)
    last = provider.user_texts[4]
    assert "Answer 0." not in last and all(f"Answer {i}." in last for i in (1, 2, 3))


def test_new_topic_forgets_earlier_answers(make_engine):
    provider = FakeProvider([["Use Redis."], ["Something else."]])
    engine, events, writer = make_engine(provider)
    engine.on_utterance(Utterance("them", "How would you cache it?", 80, 82))
    engine.ask_now()
    assert engine.wait_idle(5)
    engine.new_topic()
    engine.on_utterance(Utterance("them", "Tell me about yourself.", 90, 92))
    engine.ask_now()
    assert engine.wait_idle(5)
    assert "Use Redis." not in provider.user_texts[1]
