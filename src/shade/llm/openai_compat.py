"""OpenAI and any OpenAI-compatible service (Grok, Groq, DeepSeek, Gemini, local)."""

from __future__ import annotations

import base64
import threading
from typing import Iterator

import openai

from shade.llm.base import ProviderError
from shade.models import Usage


class OpenAIProvider:
    def __init__(
        self,
        model: str,
        detector_model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        supports_images: bool = True,
        label: str = "OpenAI",
        client=None,
    ) -> None:
        self.model = model
        self.detector_model = detector_model
        self.base_url = base_url
        self.api_key = api_key
        self.supports_images = supports_images
        self.label = label
        self.last_usage = Usage()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = openai.OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def _map_error(self, e: Exception) -> ProviderError:
        if isinstance(e, openai.AuthenticationError):
            return ProviderError(f"{self.label}: invalid API key.")
        if isinstance(e, openai.APIConnectionError):
            where = f" to {self.base_url}" if self.base_url else ""
            return ProviderError(f"{self.label}: cannot connect{where}.")
        if isinstance(e, openai.APIStatusError):
            return ProviderError(f"{self.label}: HTTP {e.status_code}.")
        return ProviderError(f"{self.label}: {e}")

    def stream_answer(
        self, system: str, user_text: str, image_png: bytes | None, cancel: threading.Event
    ) -> Iterator[str]:
        if image_png:
            data = base64.b64encode(image_png).decode("ascii")
            content = [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
                {"type": "text", "text": user_text},
            ]
        else:
            content = user_text
        self.last_usage = Usage()
        try:
            chunks = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                stream=True,
                stream_options={"include_usage": True},
            )
            for ch in chunks:
                if ch.usage:
                    self.last_usage = Usage(
                        ch.usage.prompt_tokens or 0, ch.usage.completion_tokens or 0
                    )
                if ch.choices and ch.choices[0].delta.content:
                    yield ch.choices[0].delta.content
                    if cancel.is_set():
                        return
        except openai.OpenAIError as e:
            raise self._map_error(e) from e

    def detect(self, system: str, user_text: str) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.detector_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=100,
            )
        except openai.OpenAIError as e:
            raise self._map_error(e) from e
        return resp.choices[0].message.content or ""
