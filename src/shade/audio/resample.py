"""Convert captured audio to 16 kHz mono float32."""

from __future__ import annotations

import numpy as np
import soxr

TARGET_RATE = 16000


class Resampler:
    def __init__(self, in_rate: int, channels: int) -> None:
        self.in_rate = in_rate
        self.channels = channels
        self._stream = (
            None
            if in_rate == TARGET_RATE
            else soxr.ResampleStream(in_rate, TARGET_RATE, 1, dtype="float32")
        )

    def process(self, block: np.ndarray) -> np.ndarray:
        x = np.asarray(block, dtype=np.float32)
        if x.ndim == 2:
            x = x.mean(axis=1, dtype=np.float32)
        if self._stream is None:
            return x
        return self._stream.resample_chunk(x).astype(np.float32, copy=False)
