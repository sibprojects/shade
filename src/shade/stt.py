"""Speech-to-text with faster-whisper on a single worker thread."""

from __future__ import annotations

import queue
import re
import threading
from typing import Callable

import numpy as np

from shade.models import Source, Utterance

_JUNK = {
    "you",
    "thank you",
    "thanks for watching",
    "thank you for watching",
    "bye",
    "uh",
    "um",
}


def is_junk(text: str) -> bool:
    """Empty output or a typical Whisper hallucination on silence/noise."""
    stripped = text.strip()
    if not re.search(r"\w", stripped):
        return True
    return stripped.lower().strip(".!?, ") in _JUNK


class Transcriber:
    def __init__(self, model: str, compute_type: str, device: str = "cuda") -> None:
        from shade.gpu import setup_cuda_dlls

        setup_cuda_dlls()
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            without_timestamps=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()


class SttWorker:
    def __init__(
        self,
        transcriber,
        on_utterance: Callable[[Utterance], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.on_utterance = on_utterance
        self.on_error = on_error or (lambda msg: None)
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="stt")
        self._thread.start()

    def submit(self, source: Source, audio: np.ndarray, start: float, end: float) -> None:
        self._q.put((source, audio, start, end))

    def stop(self) -> None:
        """Finish queued work, then stop."""
        self._q.put(None)
        self._thread.join()

    def _loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            source, audio, start, end = item
            try:
                text = self.transcriber.transcribe(audio)
            except Exception as e:
                self.on_error(f"Speech recognition error: {e}")
                continue
            if is_junk(text):
                continue
            self.on_utterance(Utterance(source, text.strip(), start, end))
