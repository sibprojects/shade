"""Decides whether the other side just asked a question or gave a task."""

from __future__ import annotations

from typing import Callable

from shade.llm.base import Provider, ProviderError
from shade.models import Utterance
from shade.prompt import DETECT_RULES, build_detect_text, parse_detection
from shade.rules import looks_like_question


class Detector:
    def __init__(
        self,
        provider: Provider,
        min_words: int = 3,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.provider = provider
        self.min_words = min_words
        self.on_error = on_error or (lambda msg: None)
        self._reported: set[str] = set()

    def check(self, latest: Utterance, recent: list[Utterance]) -> str | None:
        if latest.source != "them" or len(latest.text.split()) < self.min_words:
            return None
        try:
            reply = self.provider.detect(DETECT_RULES, build_detect_text(recent, latest))
        except ProviderError as e:
            # Report each distinct failure once, so a broken detector isn't silent.
            msg = f"Question detection failed: {e}"
            if msg not in self._reported:
                self._reported.add(msg)
                self.on_error(msg)
            return None
        return parse_detection(reply)


class RuleDetector:
    """Same interface as Detector, but decides by rules: no model, no cost, no delay."""

    def __init__(self, min_words: int = 3) -> None:
        self.min_words = min_words

    def check(self, latest: Utterance, recent: list[Utterance]) -> str | None:
        if latest.source != "them" or len(latest.text.split()) < self.min_words:
            return None
        return latest.text.strip() if looks_like_question(latest.text) else None
