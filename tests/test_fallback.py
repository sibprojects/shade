"""Fallback provider: when the answer model fails, another one answers."""

import threading
from dataclasses import replace
from datetime import datetime

import pytest

from shade.config import Settings, load_settings, save_settings
from shade.cost import CostMeter
from shade.engine import Engine
from shade.llm.base import ProviderError
from shade.llm.factory import UnavailableProvider, make_provider_or_unavailable
from shade.llm.fallback import RETRY_PRIMARY_S, FallbackProvider
from shade.models import HintDone, Usage, Utterance
from shade.session import SessionWriter
from shade.transcript import Transcript


class Fake:
    def __init__(self, model, chunks=None, error=None, images=True, billable=True, detect_reply="NONE"):
        self.model = model
        self.detector_model = model
        self.supports_images = images
        self.billable = billable
        self.last_usage = Usage()
        self.chunks = chunks or ["ok"]
        self.error = error
        self.detect_reply = detect_reply
        self.calls = 0
        self.closed = False

    def stream_answer(self, system, user_text, image_png, cancel):
        self.calls += 1
        for i, c in enumerate(self.chunks):
            if self.error and i == self.fail_at:
                raise self.error
            yield c
        if self.error and self.fail_at >= len(self.chunks):
            raise self.error
        self.last_usage = Usage(1000, 100)

    fail_at = 0

    def detect(self, system, user_text):
        if self.error:
            raise self.error
        return self.detect_reply

    def close(self):
        self.closed = True


def answer(p, image=None):
    return "".join(p.stream_answer("sys", "q", image, threading.Event()))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_primary_answers_when_it_works():
    primary, backup = Fake("main", ["hi"]), Fake("spare")
    p = FallbackProvider(primary, backup)
    assert answer(p) == "hi"
    assert p.model == "main"
    assert backup.calls == 0


def test_backup_answers_when_primary_fails_before_any_text():
    statuses = []
    primary = Fake("main", error=ProviderError("Claude Code: subscription usage limit reached."))
    backup = Fake("spare", ["from backup"])
    p = FallbackProvider(primary, backup, on_status=statuses.append)
    assert answer(p) == "from backup"
    assert p.model == "spare"
    assert p.last_usage == Usage(1000, 100)
    assert statuses == ["Claude Code: subscription usage limit reached. Answering with spare instead."]


def test_failure_after_text_is_not_retried():
    primary = Fake("main", ["half"], error=ProviderError("Claude Code: broke."))
    primary.fail_at = 1
    backup = Fake("spare")
    p = FallbackProvider(primary, backup)
    with pytest.raises(ProviderError):
        answer(p)
    assert backup.calls == 0


def test_backup_is_used_for_a_while_then_primary_is_tried_again():
    clock = Clock()
    statuses = []
    primary = Fake("main", ["main answer"], error=ProviderError("down"))
    backup = Fake("spare", ["spare answer"])
    p = FallbackProvider(primary, backup, on_status=statuses.append, clock=clock)
    answer(p)
    clock.t = RETRY_PRIMARY_S - 1
    assert answer(p) == "spare answer"
    assert primary.calls == 1  # not tried again yet
    assert len(statuses) == 1  # reported once
    primary.error = None
    clock.t = RETRY_PRIMARY_S + 1
    assert answer(p) == "main answer"
    assert p.model == "main"


def test_image_goes_to_backup_when_only_backup_has_vision():
    primary, backup = Fake("main", images=False), Fake("spare", ["seen"])
    p = FallbackProvider(primary, backup)
    assert p.supports_images
    assert answer(p, image=b"png") == "seen"
    assert primary.calls == 0


def test_image_failure_without_vision_backup_keeps_primary_error():
    primary = Fake("main", error=ProviderError("main down"))
    backup = Fake("spare", images=False)
    p = FallbackProvider(primary, backup)
    with pytest.raises(ProviderError, match="main down"):
        answer(p, image=b"png")
    assert backup.calls == 0


def test_detect_falls_back_too():
    primary = Fake("main", error=ProviderError("down"))
    backup = Fake("spare", detect_reply="ASK: How?")
    assert FallbackProvider(primary, backup).detect("s", "t") == "ASK: How?"


def test_close_closes_both():
    primary, backup = Fake("main"), Fake("spare")
    FallbackProvider(primary, backup).close()
    assert primary.closed and backup.closed


def test_billable_follows_the_provider_that_answered():
    primary = Fake("claude-opus-5-5", billable=False, error=ProviderError("limit"))
    backup = Fake("claude-opus-5-5", ["x"])
    p = FallbackProvider(primary, backup)
    answer(p)
    assert p.billable is True


def test_engine_does_not_charge_subscription_answers(tmp_path):
    events = []
    provider = Fake("claude-opus-5-5", ["free"], billable=False)
    engine = Engine(
        provider=provider,
        detector=None,
        transcript=Transcript(),
        writer=SessionWriter(tmp_path, "T", datetime(2026, 11, 14, 10, 0)),
        cost=CostMeter({"claude-opus-5-5": [4.0, 20.0]}),
        profile_text="",
        context_seconds=180,
        on_event=events.append,
        clock=lambda: 100.0,
    )
    engine.set_auto(False)
    engine.transcript.add(Utterance("them", "How?", 90, 91))
    engine.ask_now()
    assert engine.wait_idle(5)
    provider.billable = True
    engine.ask_now()
    assert engine.wait_idle(5)
    engine.stop()
    done = [e for e in events if isinstance(e, HintDone)]
    assert done[0].cost == 0.0
    assert done[1].cost == pytest.approx((1000 * 4.0 + 100 * 20.0) / 1e6)


# ---- settings and factory ---------------------------------------------


def test_fallback_setting_round_trips(tmp_path):
    path = tmp_path / "s.toml"
    save_settings(Settings(fallback_provider="local"), path)
    assert load_settings(path).fallback_provider == "local"
    assert Settings().fallback_provider == ""


def test_factory_wraps_with_fallback():
    s = Settings(provider="local", fallback_provider="network")
    provider, problem = make_provider_or_unavailable(s)
    assert problem is None
    assert isinstance(provider, FallbackProvider)
    assert provider.primary.model == s.presets["local"]["model"]
    assert provider.backup.model == s.presets["network"]["model"]


def test_factory_without_fallback_or_same_provider_does_not_wrap():
    for fb in ("", "local"):
        provider, _ = make_provider_or_unavailable(Settings(provider="local", fallback_provider=fb))
        assert not isinstance(provider, FallbackProvider)


def test_unavailable_primary_still_answers_through_backup(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings(provider="openai", fallback_provider="local")
    provider, problem = make_provider_or_unavailable(s)
    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider.primary, UnavailableProvider)
    assert "OPENAI_API_KEY" in problem


def test_unavailable_backup_is_reported_and_primary_kept(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings(provider="local", fallback_provider="openai")
    provider, problem = make_provider_or_unavailable(s)
    assert not isinstance(provider, FallbackProvider)
    assert problem.startswith("Fallback model unavailable:")


def test_settings_dialog_has_fallback_choice(qtbot):
    from shade.ui.settings_dialog import SettingsDialog

    d = SettingsDialog(Settings(provider="claude_code"), {}, start_meter=False)
    qtbot.addWidget(d)
    assert d.fallback.currentData() == ""
    d.fallback.setCurrentIndex(d.fallback.findData("claude"))
    assert d.result_settings().fallback_provider == "claude"
    assert replace(d.result_settings(), fallback_provider="").provider == "claude_code"
