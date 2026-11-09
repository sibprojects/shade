"""Cuts a continuous 16 kHz stream into utterances using a VAD."""

from __future__ import annotations

from collections import deque
from typing import Callable

import numpy as np

from shade.models import Source

RATE = 16000
CHUNK = 512
CHUNK_S = CHUNK / RATE


class Segmenter:
    def __init__(
        self,
        source: Source,
        speech_prob: Callable[[np.ndarray], float],
        on_utterance: Callable[[Source, np.ndarray, float, float], None],
        silence_ms: int = 600,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        max_utterance_s: float = 20.0,
        pre_roll_ms: int = 200,
    ) -> None:
        self.source = source
        self.speech_prob = speech_prob
        self.on_utterance = on_utterance
        self.threshold = threshold
        self.neg_threshold = threshold - 0.15
        self.silence_chunks = max(1, round(silence_ms / 1000 / CHUNK_S))
        self.min_voiced = max(1, round(min_speech_ms / 1000 / CHUNK_S))
        self.max_chunks = int(max_utterance_s / CHUNK_S)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=round(pre_roll_ms / 1000 / CHUNK_S))
        self._buf = np.zeros(0, dtype=np.float32)
        self._buf_t = 0.0  # session time of the first sample in _buf
        self._reset_utterance()

    def _reset_utterance(self) -> None:
        self._speaking = False
        self._chunks: list[np.ndarray] = []
        self._start = 0.0
        self._voiced = 0
        self._last_voiced_idx = -1  # index in _chunks of the last voiced chunk
        self._silence_run = 0

    def feed(self, samples: np.ndarray, t0: float) -> None:
        if len(self._buf) == 0:
            self._buf_t = t0
        self._buf = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32)])
        while len(self._buf) >= CHUNK:
            chunk, self._buf = self._buf[:CHUNK], self._buf[CHUNK:]
            t = self._buf_t
            self._buf_t += CHUNK_S
            self._process(chunk, t)

    def _process(self, chunk: np.ndarray, t: float) -> None:
        p = self.speech_prob(chunk)
        if not self._speaking:
            if p >= self.threshold:
                self._speaking = True
                self._chunks = list(self._pre_roll)
                self._start = t - len(self._chunks) * CHUNK_S
                self._chunks.append(chunk)
                self._voiced = 1
                self._last_voiced_idx = len(self._chunks) - 1
                self._silence_run = 0
                self._pre_roll.clear()
            else:
                self._pre_roll.append(chunk)
            return

        self._chunks.append(chunk)
        if p >= self.neg_threshold:
            self._silence_run = 0
            if p >= self.threshold:
                self._voiced += 1
            self._last_voiced_idx = len(self._chunks) - 1
        else:
            self._silence_run += 1

        if self._silence_run >= self.silence_chunks:
            self._emit()
        elif len(self._chunks) >= self.max_chunks:
            self._last_voiced_idx = len(self._chunks) - 1
            self._emit(force=True)

    def _emit(self, force: bool = False) -> None:
        if force or self._voiced >= self.min_voiced:
            kept = self._chunks[: self._last_voiced_idx + 1]
            audio = np.concatenate(kept)
            end = self._start + len(kept) * CHUNK_S
            self.on_utterance(self.source, audio, self._start, end)
        self._reset_utterance()
