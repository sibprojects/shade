import json
import sys
import threading
from pathlib import Path

import pytest

from shade.config import Settings, auto_allowed, billable_prices, stt_config
from shade.llm.base import ProviderError
from shade.llm.claude_code import ClaudeCodeProvider
from shade.llm.factory import make_provider_or_unavailable

FAKE = [sys.executable, str(Path(__file__).parent / "fakes" / "fake_claude.py")]


@pytest.fixture
def cc():
    p = ClaudeCodeProvider("claude-sonnet-5-5", "claude-haiku-5-5", "low", command=FAKE)
    yield p
    p.close()


def _answer(p, text="Q?", image=None, cancel=None):
    out = "".join(p.stream_answer("SYS", text, image, cancel or threading.Event()))
    return out, json.loads(out[out.index("{"):])


def test_streams_answer_and_usage(cc):
    out, info = _answer(cc)
    assert out.startswith("Hello world ")
    assert info["model"] == "claude-sonnet-5-5" and info["effort"] == "low"
    assert info["system"] == "SYS" and info["tools"] == ""
    assert (cc.last_usage.input_tokens, cc.last_usage.output_tokens, cc.last_usage.cache_read_tokens) == (7, 11, 5)


def test_screenshot_goes_in_the_message(cc):
    _, info = _answer(cc, image=b"\x89PNG fake")
    assert info["images"] == 1


def test_api_key_is_not_passed_so_the_subscription_is_used(cc, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    _, info = _answer(cc)
    assert info["has_key"] is False


def test_next_process_is_started_in_advance(cc):
    _, first = _answer(cc)
    spare = cc.spare_pid("claude-sonnet-5-5", "low", "SYS")
    assert spare is not None and spare not in (first["pid"], first["ppid"])
    _, second = _answer(cc)
    assert spare in (second["pid"], second["ppid"])


def test_close_stops_the_waiting_processes(cc):
    _answer(cc)
    procs = cc.spare_processes()
    assert procs
    cc.close()
    for p in procs:
        assert p.wait(timeout=5) is not None


def test_not_signed_in_is_explained(cc):
    with pytest.raises(ProviderError, match="sign in"):
        _answer(cc, "FAIL_LOGIN")


def test_usage_limit_is_explained(cc):
    with pytest.raises(ProviderError, match="usage limit"):
        _answer(cc, "FAIL_LIMIT")


def test_crash_is_reported(cc):
    with pytest.raises(ProviderError, match="Claude Code"):
        _answer(cc, "CRASH")


def test_cancel_stops_the_stream(cc):
    cancel = threading.Event()
    got = []
    for chunk in cc.stream_answer("SYS", "SLOW", None, cancel):
        got.append(chunk)
        if len(got) == 2:
            cancel.set()
    assert len(got) == 2


def test_detect_uses_the_detector_model(cc):
    text = cc.detect("DSYS", "is this a question?")
    assert json.loads(text[text.index("{"):])["model"] == "claude-haiku-5-5"


def test_factory_reports_missing_claude_code():
    s = Settings(provider="claude_code", cc_path=r"C:\nowhere\claude.exe")
    provider, problem = make_provider_or_unavailable(s)
    assert problem and "Claude Code not found" in problem


def test_speech_model_stays_full_with_claude_code():
    assert stt_config(Settings(provider="claude_code")) == ("large-v3-turbo", "float16")


def test_auto_hints_need_permission_with_claude_code():
    assert auto_allowed(Settings())
    assert not auto_allowed(Settings(provider="claude_code", cc_auto=False))
    assert auto_allowed(Settings(provider="claude_code", cc_auto=True))


def test_subscription_answers_cost_nothing_extra():
    assert billable_prices(Settings(provider="claude_code")) == {}
    assert billable_prices(Settings()) == Settings().prices
