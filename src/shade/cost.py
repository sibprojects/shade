"""Running API cost for a session."""

from __future__ import annotations

import threading

from shade.models import Usage


class CostMeter:
    def __init__(self, prices: dict[str, list[float]]) -> None:
        self._prices = prices  # USD per 1M tokens: [input, output]
        self._total = 0.0
        self._lock = threading.Lock()

    def add(self, model: str, usage: Usage) -> float:
        price = self._prices.get(model)
        if not price:
            return 0.0
        p_in, p_out = price
        cost = (
            usage.input_tokens * p_in
            + usage.output_tokens * p_out
            + usage.cache_read_tokens * 0.1 * p_in
        ) / 1e6
        with self._lock:
            self._total += cost
        return cost

    @property
    def total(self) -> float:
        return self._total
