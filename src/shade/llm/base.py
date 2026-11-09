"""Common provider interface."""

from __future__ import annotations

import threading
from typing import Iterator, Protocol

from shade.models import Usage


class ProviderError(Exception):
    """A user-facing provider failure; str(e) is shown in the hint area."""


class Provider(Protocol):
    model: str
    detector_model: str
    supports_images: bool
    last_usage: Usage

    def stream_answer(
        self, system: str, user_text: str, image_png: bytes | None, cancel: threading.Event
    ) -> Iterator[str]: ...

    def detect(self, system: str, user_text: str) -> str: ...
