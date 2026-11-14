"""A provider that switches to a backup when the answer model fails.

Typical case: Claude Code hits the subscription usage limit in the middle of a
call, and the answers continue on the Claude API or a local model. After a
failure the backup answers for a while; then the main model is tried again.
An answer that already started streaming is never restarted on the backup.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Iterator

from shade.llm.base import Provider, ProviderError
from shade.models import Usage

RETRY_PRIMARY_S = 300.0  # after a failure, the backup answers this long


def provider_name(p: Provider) -> str:
    return getattr(p, "label", None) or p.model


class FallbackProvider:
    def __init__(
        self,
        primary: Provider,
        backup: Provider,
        on_status: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.primary = primary
        self.backup = backup
        self.on_status = on_status or (lambda msg: None)
        self.clock = clock
        self._active: Provider = primary
        self._failed_at: float | None = None
        self._lock = threading.Lock()

    # Attributes the engine reads, taken from whichever provider answered last.
    @property
    def model(self) -> str:
        return self._active.model

    @property
    def detector_model(self) -> str:
        return self.primary.detector_model

    @property
    def supports_images(self) -> bool:
        return self.primary.supports_images or self.backup.supports_images

    @property
    def last_usage(self) -> Usage:
        return self._active.last_usage

    @property
    def billable(self) -> bool:
        return getattr(self._active, "billable", True)

    def _primary_resting(self) -> bool:
        with self._lock:
            return self._failed_at is not None and self.clock() - self._failed_at < RETRY_PRIMARY_S

    def _primary_failed(self, e: ProviderError) -> None:
        with self._lock:
            already = self._failed_at is not None  # still failing: said so before
            self._failed_at = self.clock()
        if not already:
            self.on_status(f"{str(e).rstrip('.')}. Answering with {provider_name(self.backup)} instead.")

    def stream_answer(
        self, system: str, user_text: str, image_png: bytes | None, cancel: threading.Event
    ) -> Iterator[str]:
        use_primary = not self._primary_resting() and (image_png is None or self.primary.supports_images)
        if use_primary:
            self._active = self.primary
            started = False
            try:
                for text in self.primary.stream_answer(system, user_text, image_png, cancel):
                    started = True
                    yield text
                with self._lock:
                    self._failed_at = None  # working again
                return
            except ProviderError as e:
                if started or (image_png is not None and not self.backup.supports_images):
                    raise
                self._primary_failed(e)
        self._active = self.backup
        yield from self.backup.stream_answer(system, user_text, image_png, cancel)

    def detect(self, system: str, user_text: str) -> str:
        if not self._primary_resting():
            try:
                return self.primary.detect(system, user_text)
            except ProviderError:
                pass
        return self.backup.detect(system, user_text)

    def close(self) -> None:
        for p in (self.primary, self.backup):
            close = getattr(p, "close", None)
            if close is not None:
                close()
