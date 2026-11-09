import threading
from types import SimpleNamespace as NS

import anthropic
import httpx2 as httpx
import openai
import pytest

from shade.config import Settings
from shade.llm.base import ProviderError
from shade.llm.claude import ClaudeProvider
from shade.llm.factory import make_provider
from shade.llm.openai_compat import OpenAIProvider
from shade.models import Usage

REQ = httpx.Request("POST", "https://example.test")


# ---------- fake Anthropic client ----------


class FakeStream:
    def __init__(self, chunks, usage, stop_reason="end_turn", on_chunk=None):
        self.chunks = chunks
        self.usage = usage
        self.stop_reason = stop_reason
        self.on_chunk = on_chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        for c in self.chunks:
            if self.on_chunk:
                self.on_chunk(c)
            yield c

    def get_final_message(self):
        return NS(usage=self.usage, stop_reason=self.stop_reason)


class FakeMessages:
    def __init__(self, stream=None, create_text="NONE", error=None):
        self._stream = stream
        self._create_text = create_text
        self._error = error
        self.calls = []

    def stream(self, **kw):
        self.calls.append(kw)
        if self._error:
            raise self._error
        return self._stream

    def create(self, **kw):
        self.calls.append(kw)
        if self._error:
            raise self._error
        return NS(content=[NS(type="text", text=self._create_text)])


def fake_anthropic(stream=None, error=None, create_text="NONE"):
    std = FakeMessages(stream, create_text, error)
    beta = FakeMessages(stream, create_text, error)
    return NS(messages=std, beta=NS(messages=beta))


def a_usage(i=10, o=2, c=8):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=c)


def claude(client, model="claude-haiku-5-5"):
    return ClaudeProvider(model, "claude-haiku-5-5", "low", client=client)


def test_claude_stream_yields_text_and_usage():
    client = fake_anthropic(FakeStream(["Hel", "lo"], a_usage()))
    p = claude(client)
    assert "".join(p.stream_answer("sys", "user", None, threading.Event())) == "Hello"
    assert p.last_usage == Usage(10, 2, 8)


def test_claude_sends_cached_system_and_image():
    client = fake_anthropic(FakeStream(["x"], a_usage()))
    p = claude(client)
    list(p.stream_answer("sys", "user", b"\x89PNG", threading.Event()))
    kw = client.messages.calls[0]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    content = kw["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[1] == {"type": "text", "text": "user"}
    assert kw["output_config"] == {"effort": "low"}


def test_claude_opus_uses_fallbacks():
    client = fake_anthropic(FakeStream(["x"], a_usage()))
    p = claude(client, model="claude-opus-5-5")
    list(p.stream_answer("sys", "user", None, threading.Event()))
    assert client.messages.calls == []
    kw = client.beta.messages.calls[0]
    assert kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]


def test_claude_cancel_stops_early():
    cancel = threading.Event()
    client = fake_anthropic(FakeStream(["a", "b", "c"], a_usage(), on_chunk=lambda c: cancel.set()))
    p = claude(client)
    assert list(p.stream_answer("sys", "user", None, cancel)) == ["a"]


def test_claude_refusal_raises():
    client = fake_anthropic(FakeStream([], a_usage(), stop_reason="refusal"))
    with pytest.raises(ProviderError, match="Model declined to answer."):
        list(claude(client).stream_answer("sys", "user", None, threading.Event()))


def test_claude_auth_error_maps():
    err = anthropic.AuthenticationError(
        "bad key", response=httpx.Response(401, request=REQ), body=None
    )
    p = claude(fake_anthropic(error=err))
    with pytest.raises(ProviderError) as e:
        list(p.stream_answer("sys", "user", None, threading.Event()))
    assert str(e.value) == "Claude: invalid or missing ANTHROPIC_API_KEY."


def test_claude_detect_returns_text():
    client = fake_anthropic(create_text="ASK: Why?")
    assert claude(client).detect("rules", "text") == "ASK: Why?"
    assert client.messages.calls[0]["model"] == "claude-haiku-5-5"


# ---------- fake OpenAI client ----------


def chunk(text=None, usage=None):
    choices = [NS(delta=NS(content=text))] if text is not None else []
    return NS(choices=choices, usage=usage)


class FakeCompletions:
    def __init__(self, chunks=None, error=None, reply="NONE"):
        self.chunks = chunks or []
        self.error = error
        self.reply = reply
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        if kw.get("stream"):
            return iter(self.chunks)
        return NS(choices=[NS(message=NS(content=self.reply))])


def fake_openai(**kw):
    comp = FakeCompletions(**kw)
    return NS(chat=NS(completions=comp)), comp


def test_openai_stream_and_usage():
    client, comp = fake_openai(
        chunks=[chunk("Hi"), chunk(" there"), chunk(usage=NS(prompt_tokens=7, completion_tokens=3))]
    )
    p = OpenAIProvider("gpt-x", "gpt-x", client=client)
    assert "".join(p.stream_answer("sys", "user", b"png", threading.Event())) == "Hi there"
    assert p.last_usage == Usage(7, 3)
    kw = comp.calls[0]
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert kw["stream_options"] == {"include_usage": True}


def test_local_connect_error_message():
    client, _ = fake_openai(error=openai.APIConnectionError(request=REQ))
    p = OpenAIProvider(
        "m", "m", base_url="http://localhost:11434/v1", label="Local model", client=client
    )
    with pytest.raises(ProviderError) as e:
        list(p.stream_answer("sys", "user", None, threading.Event()))
    assert str(e.value) == "Local model: cannot connect to http://localhost:11434/v1."


def test_factory_local_flags():
    s = Settings(provider="local")
    s.presets["local"]["supports_images"] = False
    assert make_provider(s).supports_images is False


def test_factory_grok_uses_preset(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "x")
    p = make_provider(Settings(provider="grok"))
    assert p.base_url == "https://api.x.ai/v1"
    assert p.label == "Grok (xAI)"


def test_factory_missing_key_message(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProviderError) as e:
        make_provider(Settings(provider="deepseek"))
    assert str(e.value) == "DeepSeek: set DEEPSEEK_API_KEY."


def test_factory_unknown_provider():
    with pytest.raises(ProviderError, match="Unknown provider: nope"):
        make_provider(Settings(provider="nope"))
