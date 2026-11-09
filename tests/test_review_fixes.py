"""Regression tests for the final-review findings."""

import threading
import time
from datetime import datetime
from types import SimpleNamespace as NS

import numpy as np
import pytest

from shade.config import Settings
from shade.cost import CostMeter
from shade.detect import Detector
from shade.engine import Engine
from shade.llm.base import ProviderError
from shade.llm.claude import ClaudeProvider
from shade.llm.factory import UnavailableProvider, make_provider_or_unavailable
from shade.llm.openai_compat import OpenAIProvider
from shade.models import HintStarted, Status, Usage, Utterance
from shade.session import SessionWriter
from shade.stt import SttWorker
from shade.transcript import Transcript


# ---- 1. missing Anthropic credentials ------------------------------------


class RaisingMessages:
    def __init__(self, exc):
        self.exc = exc

    def stream(self, **kw):
        raise self.exc

    def create(self, **kw):
        raise self.exc


def test_claude_missing_credentials_maps_to_key_message():
    exc = TypeError("Could not resolve authentication method. Expected one of api_key, auth_token")
    client = NS(messages=RaisingMessages(exc), beta=NS(messages=RaisingMessages(exc)))
    p = ClaudeProvider("claude-haiku-5-5", "claude-haiku-5-5", "low", client=client)
    with pytest.raises(ProviderError) as e:
        list(p.stream_answer("s", "u", None, threading.Event()))
    assert str(e.value) == "Claude: invalid or missing ANTHROPIC_API_KEY."
    with pytest.raises(ProviderError):
        p.detect("s", "u")


# ---- 2. stop while a hint streams ----------------------------------------


class GatedProvider:
    model = detector_model = "fake"
    supports_images = True

    def __init__(self, gate):
        self.gate = gate
        self.last_usage = Usage()

    def stream_answer(self, system, user_text, image, cancel):
        yield "partial"
        self.gate.wait(5)
        if cancel.is_set():
            return
        yield " rest"

    def detect(self, s, u):
        return "NONE"


class AlwaysAsk:
    def check(self, latest, recent):
        return "Q?" if latest.source == "them" else None


def _engine(tmp_path, provider, detector=None, now=100.0):
    events = []
    writer = SessionWriter(tmp_path, "T", datetime(2026, 11, 9, 10, 0))
    eng = Engine(
        provider=provider, detector=detector or AlwaysAsk(), transcript=Transcript(),
        writer=writer, cost=CostMeter({}), profile_text="p", context_seconds=180,
        on_event=events.append, clock=lambda: now,
    )
    return eng, events, writer


def test_stop_mid_stream_saves_partial_without_internal_error(tmp_path):
    gate = threading.Event()
    eng, events, writer = _engine(tmp_path, GatedProvider(gate))
    eng.transcript.add(Utterance("them", "Q?", 90, 92))
    eng.ask_now()
    deadline = time.monotonic() + 5
    while not any(getattr(e, "text", None) == "partial" for e in events) and time.monotonic() < deadline:
        time.sleep(0.01)
    threading.Timer(0.2, gate.set).start()
    eng.stop()
    writer.close()
    assert not any(isinstance(e, Status) and e.message.startswith("Internal error") for e in events)
    assert "partial _(cancelled)_" in (writer.dir / "hints.md").read_text(encoding="utf-8")


def test_no_new_hint_after_stop(tmp_path):
    eng, events, writer = _engine(tmp_path, GatedProvider(threading.Event()))
    eng.stop()
    eng.transcript.add(Utterance("them", "Q?", 90, 92))
    eng.ask_now()
    assert not any(isinstance(e, HintStarted) for e in events)
    writer.close()


def test_writer_ignores_writes_after_close(tmp_path):
    w = SessionWriter(tmp_path, "T", datetime(2026, 11, 9, 10, 0))
    w.close()
    w.write_utterance(Utterance("me", "late", 1, 2))  # must not raise


# ---- 3. timeouts and stale detections ------------------------------------


def test_clients_built_with_short_timeouts(monkeypatch):
    seen = {}

    class FakeAnthropic:
        def __init__(self, **kw):
            seen["anthropic"] = kw

    class FakeOpenAI:
        def __init__(self, **kw):
            seen["openai"] = kw

    monkeypatch.setattr("shade.llm.claude.anthropic.Anthropic", FakeAnthropic)
    monkeypatch.setattr("shade.llm.openai_compat.openai.OpenAI", FakeOpenAI)
    ClaudeProvider("m", "d", "low").client
    OpenAIProvider("m", "d", base_url="http://x/v1", api_key="k").client
    for kw in seen.values():
        assert kw["timeout"] <= 30
        assert kw["max_retries"] <= 1


def test_stale_utterance_not_detected(tmp_path):
    calls = []

    class Counting:
        def check(self, latest, recent):
            calls.append(latest)
            return None

    eng, events, writer = _engine(tmp_path, GatedProvider(threading.Event()), Counting(), now=100.0)
    eng._detect(Utterance("them", "How do you test it?", 70, 80))  # ended 20 s ago
    assert calls == []
    eng.stop()
    writer.close()


# ---- 4. Claude detector token budget -------------------------------------


def test_claude_detect_leaves_room_for_thinking():
    calls = []

    class M:
        def create(self, **kw):
            calls.append(kw)
            return NS(content=[NS(type="text", text="NONE")])

    p = ClaudeProvider("m", "claude-haiku-5-5", "low", client=NS(messages=M(), beta=NS(messages=M())))
    p.detect("s", "u")
    assert calls[0]["max_tokens"] >= 512


# ---- 5. OpenAI detect params + surfaced detection errors -----------------


def test_openai_detect_sends_no_max_tokens():
    calls = []

    class C:
        def create(self, **kw):
            calls.append(kw)
            return NS(choices=[NS(message=NS(content="NONE"))])

    p = OpenAIProvider("m", "d", client=NS(chat=NS(completions=C())))
    p.detect("s", "u")
    assert "max_tokens" not in calls[0]


def test_detection_error_reported_once():
    class P:
        def detect(self, s, u):
            raise ProviderError("OpenAI: HTTP 400.")

    errors = []
    d = Detector(P(), on_error=errors.append)
    for _ in range(3):
        d.check(Utterance("them", "How do you deploy it?", 0, 1), [])
    assert errors == ["Question detection failed: OpenAI: HTTP 400."]


# ---- 6. missing key still starts transcription ---------------------------


def test_missing_preset_key_gives_unavailable_provider(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider, message = make_provider_or_unavailable(Settings(provider="deepseek"))
    assert isinstance(provider, UnavailableProvider)
    assert message == "DeepSeek: set DEEPSEEK_API_KEY."
    with pytest.raises(ProviderError, match="DeepSeek: set DEEPSEEK_API_KEY."):
        list(provider.stream_answer("s", "u", None, threading.Event()))
    with pytest.raises(ProviderError):
        provider.detect("s", "u")


# ---- 7. hotkey finds the question after the user's own filler ------------


def test_last_question_skips_trailing_me():
    t = Transcript()
    t.add(Utterance("them", "How would you scale it?", 0, 2))
    t.add(Utterance("me", "Good question, let me think", 3, 5))
    assert t.last_question() == "How would you scale it?"


# ---- 8. failures inside the audio/STT chain are reported -----------------


def test_stt_worker_survives_on_utterance_error():
    class T:
        def transcribe(self, audio):
            return "Hello there friend"

    got, errors = [], []

    def on_utt(u):
        if not got and not errors:
            raise OSError("disk full")
        got.append(u)

    w = SttWorker(T(), on_utt, on_error=errors.append)
    w.submit("me", np.zeros(10, dtype=np.float32), 0, 1)
    w.submit("me", np.zeros(10, dtype=np.float32), 1, 2)
    w.stop()
    assert errors == ["Transcript error: disk full"]
    assert len(got) == 1


def test_capture_deliver_error_reported():
    from shade.audio.capture import MicSource

    errors = []
    src = MicSource(on_error=errors.append, clock=lambda: 1.0)

    class Boom:
        def process(self, block):
            raise RuntimeError("resample failed")

    src._resampler = Boom()
    src._on_audio = lambda a, t: None
    src._deliver(np.zeros(10, dtype=np.float32), 16000)  # must not raise
    assert errors == ["Microphone unavailable: resample failed"]
