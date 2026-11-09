"""Decides whether the other side just asked a question or gave a task."""

from __future__ import annotations

from shade.llm.base import Provider, ProviderError
from shade.models import Utterance
from shade.prompt import DETECT_RULES, build_detect_text, parse_detection


class Detector:
    def __init__(self, provider: Provider, min_words: int = 3) -> None:
        self.provider = provider
        self.min_words = min_words

    def check(self, latest: Utterance, recent: list[Utterance]) -> str | None:
        if latest.source != "them" or len(latest.text.split()) < self.min_words:
            return None
        try:
            reply = self.provider.detect(DETECT_RULES, build_detect_text(recent, latest))
        except ProviderError:
            return None  # detection failures stay silent; answer failures are shown
        return parse_detection(reply)
