"""Microphone and system-audio (WASAPI loopback) capture.

Both sources deliver 16 kHz mono float32 blocks together with the session
time of the block's first sample. Device errors are reported through
on_error and never raised, so the other source keeps running.
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np

from shade.audio.resample import TARGET_RATE, Resampler

OnAudio = Callable[[np.ndarray, float], None]


def list_devices() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"mic": [], "loopback": []}
    try:
        import sounddevice as sd

        result["mic"] = sorted(
            {d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0}
        )
    except Exception:
        pass
    try:
        import pyaudiowpatch as pyaudio

        p = pyaudio.PyAudio()
        try:
            result["loopback"] = [d["name"] for d in p.get_loopback_device_info_generator()]
        finally:
            p.terminate()
    except Exception:
        pass
    return result


class _Source:
    label = "Audio"

    def __init__(
        self,
        device: str | None = None,
        on_error: Callable[[str], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.device = device
        self.on_error = on_error or (lambda msg: None)
        start = time.monotonic()
        self.clock = clock or (lambda: time.monotonic() - start)
        self._on_audio: OnAudio | None = None
        self._resampler: Resampler | None = None

    def _deliver(self, block: np.ndarray, in_rate: int) -> None:
        # Time of the block's first sample = now minus the block duration.
        t0 = self.clock() - len(block) / in_rate
        out = self._resampler.process(block)
        if len(out) and self._on_audio:
            self._on_audio(out, t0)

    def _fail(self, e: Exception) -> None:
        self.on_error(f"{self.label} unavailable: {e}")


class MicSource(_Source):
    label = "Microphone"

    def start(self, on_audio: OnAudio) -> None:
        self._on_audio = on_audio
        try:
            import sounddevice as sd

            info = sd.query_devices(self.device, kind="input")
            rate = int(info["default_samplerate"])
            self._resampler = Resampler(rate, 1)

            def callback(indata, frames, time_info, status):
                self._deliver(indata[:, 0].copy(), rate)

            self._stream = sd.InputStream(
                device=self.device, channels=1, samplerate=rate, dtype="float32",
                blocksize=int(rate * 0.05), callback=callback,
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            self._fail(e)

    def stop(self) -> None:
        if getattr(self, "_stream", None):
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class LoopbackSource(_Source):
    label = "System audio"

    def _find_device(self, pa, pyaudio) -> dict:
        loopbacks = list(pa.get_loopback_device_info_generator())
        if self.device:
            for d in loopbacks:
                if d["name"] == self.device:
                    return d
            raise RuntimeError(f"loopback device not found: {self.device}")
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if speakers.get("isLoopbackDevice"):
            return speakers
        for d in loopbacks:
            if speakers["name"] in d["name"]:
                return d
        raise RuntimeError("no loopback device for the default output")

    def start(self, on_audio: OnAudio) -> None:
        self._on_audio = on_audio
        try:
            import pyaudiowpatch as pyaudio

            self._pa = pyaudio.PyAudio()
            dev = self._find_device(self._pa, pyaudio)
            rate = int(dev["defaultSampleRate"])
            channels = int(dev["maxInputChannels"])
            self._resampler = Resampler(rate, channels)

            def callback(in_data, frame_count, time_info, status):
                block = np.frombuffer(in_data, dtype=np.float32).reshape(-1, channels)
                self._deliver(block, rate)
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(
                format=pyaudio.paFloat32, channels=channels, rate=rate, input=True,
                input_device_index=dev["index"], frames_per_buffer=int(rate * 0.05),
                stream_callback=callback,
            )
            self._stream.start_stream()
        except Exception as e:
            self._stream = None
            self._fail(e)

    def stop(self) -> None:
        if getattr(self, "_stream", None):
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if getattr(self, "_pa", None):
            self._pa.terminate()
            self._pa = None


__all__ = ["MicSource", "LoopbackSource", "list_devices", "TARGET_RATE"]
