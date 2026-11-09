"""Manual check: live transcript of mic (Me) and system audio (Them) in the console.

    uv run python scripts/smoke_audio.py [--model distil-large-v3] [--compute float16]

Speak into the mic and play a video; press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import time

from shade.audio.capture import LoopbackSource, MicSource
from shade.audio.segmenter import Segmenter
from shade.audio.vad import SileroVad
from shade.stt import SttWorker, Transcriber
from shade.transcript import format_lines


class TimedTranscriber:
    def __init__(self, inner: Transcriber) -> None:
        self.inner = inner
        self.last = 0.0

    def transcribe(self, audio):
        t = time.perf_counter()
        text = self.inner.transcribe(audio)
        self.last = time.perf_counter() - t
        return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="distil-large-v3")
    ap.add_argument("--compute", default="float16")
    args = ap.parse_args()

    print(f"Loading {args.model} ({args.compute})...")
    t = time.perf_counter()
    transcriber = TimedTranscriber(Transcriber(args.model, args.compute))
    print(f"Loaded in {time.perf_counter() - t:.1f}s. Listening; Ctrl+C to stop.")

    start = time.monotonic()
    clock = lambda: time.monotonic() - start  # noqa: E731

    def show(u):
        audio_s = u.end - u.start
        print(f"{format_lines([u])}   (audio {audio_s:.1f}s, stt {transcriber.last:.2f}s)")

    worker = SttWorker(transcriber, show, on_error=print)
    sources = []
    for name, cls in (("me", MicSource), ("them", LoopbackSource)):
        seg = Segmenter(name, SileroVad(), worker.submit)
        src = cls(on_error=print, clock=clock)
        src.start(seg.feed)
        sources.append(src)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for s in sources:
            s.stop()
        worker.stop()


if __name__ == "__main__":
    main()
