"""Claude (Anthropic API) provider."""

from __future__ import annotations

import base64
import threading
from typing import Iterator

import anthropic

from shade.llm.base import ProviderError
from shade.models import Usage

# Models that accept server-side refusal fallbacks.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-opus-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


ANSWER_TIMEOUT = 30.0
DETECT_TIMEOUT = 10.0
KEY_MESSAGE = "Claude: invalid or missing ANTHROPIC_API_KEY."


def _map_error(e: Exception) -> ProviderError:
    if isinstance(e, ProviderError):
        return e
    if isinstance(e, anthropic.AuthenticationError) or (
        isinstance(e, TypeError) and "authentication" in str(e).lower()
    ):
        return ProviderError(KEY_MESSAGE)
    if isinstance(e, anthropic.APIConnectionError):
        return ProviderError("Claude: cannot connect.")
    if isinstance(e, anthropic.APIStatusError):
        return ProviderError(f"Claude: HTTP {e.status_code}.")
    return ProviderError(f"Claude: {e}")


class ClaudeProvider:
    supports_images = True

    def __init__(self, model: str, detector_model: str, effort: str, client=None) -> None:
        self.model = model
        self.detector_model = detector_model
        self.effort = effort
        self.last_usage = Usage()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = anthropic.Anthropic(timeout=ANSWER_TIMEOUT, max_retries=1)
        return self._client

    def stream_answer(
        self, system: str, user_text: str, image_png: bytes | None, cancel: threading.Event
    ) -> Iterator[str]:
        content: list[dict] = []
        if image_png:
            data = base64.b64encode(image_png).decode("ascii")
            content.append(
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}
            )
        content.append({"type": "text", "text": user_text})
        kwargs = dict(
            model=self.model,
            max_tokens=4096,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort},
        )
        self.last_usage = Usage()
        try:
            if self.model in FALLBACK_MODELS:
                manager = self.client.beta.messages.stream(
                    **kwargs, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                manager = self.client.messages.stream(**kwargs)
            with manager as stream:
                for text in stream.text_stream:
                    yield text
                    if cancel.is_set():
                        return
                final = stream.get_final_message()
        except Exception as e:  # SDK raises TypeError (not AnthropicError) for missing credentials
            raise _map_error(e) from e
        u = final.usage
        self.last_usage = Usage(
            u.input_tokens or 0, u.output_tokens or 0, getattr(u, "cache_read_input_tokens", 0) or 0
        )
        if final.stop_reason == "refusal":
            raise ProviderError("Model declined to answer.")

    def detect(self, system: str, user_text: str) -> str:
        try:
            client = self.client
            if hasattr(client, "with_options"):
                client = client.with_options(timeout=DETECT_TIMEOUT)
            msg = client.messages.create(
                model=self.detector_model,
                # Room for adaptive thinking, which counts toward max_tokens.
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_text}],
                output_config={"effort": "low"},
            )
        except Exception as e:
            raise _map_error(e) from e
        return "".join(b.text for b in msg.content if b.type == "text")
