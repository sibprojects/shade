"""Build the provider selected in settings."""

from __future__ import annotations

import os

from shade.config import Settings
from shade.llm.base import Provider, ProviderError
from shade.llm.claude import ClaudeProvider
from shade.llm.openai_compat import OpenAIProvider
from shade.models import Usage


class UnavailableProvider:
    """Stands in when the provider can't be built (e.g. missing key), so the
    session still transcribes and every hint shows the reason."""

    supports_images = True
    detector_model = ""

    def __init__(self, message: str, model: str = "") -> None:
        self.message = message
        self.model = model
        self.last_usage = Usage()

    def stream_answer(self, system, user_text, image_png, cancel):
        raise ProviderError(self.message)
        yield  # pragma: no cover  (makes this a generator)

    def detect(self, system, user_text):
        raise ProviderError(self.message)


def make_provider_or_unavailable(s: Settings) -> tuple[Provider, str | None]:
    try:
        return make_provider(s), None
    except ProviderError as e:
        return UnavailableProvider(str(e)), str(e)


def make_provider(s: Settings) -> Provider:
    if s.provider == "claude":
        return ClaudeProvider(s.claude_model, s.claude_detector_model, s.claude_effort)
    p = s.presets.get(s.provider)
    if p is None:
        raise ProviderError(f"Unknown provider: {s.provider}")
    key_env = p.get("key_env") or ""
    if key_env:
        api_key = os.environ.get(key_env)
        if not api_key:
            raise ProviderError(f"{p['label']}: set {key_env}.")
    else:
        api_key = "local"
    return OpenAIProvider(
        p["model"],
        p.get("detector_model") or p["model"],
        base_url=p["base_url"],
        api_key=api_key,
        supports_images=bool(p.get("supports_images", True)),
        label=p["label"],
    )
