"""Microphone and system-audio (WASAPI loopback) capture.

Both sources deliver 16 kHz mono float32 blocks together with the session
time of the block's first sample. Device errors are reported through
on_error and never raised, so the other source keeps running.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import numpy as np

from shade.audio.resample import TARGET_RATE, Resampler

OnAudio = Callable[[np.ndarray, float], None]

def level_percent(peak: float) -> int:
    """Peak amplitude -> 0..100 on a -60..0 dBFS scale (for a level meter)."""
    if peak <= 0:
        return 0
    db = 20 * np.log10(min(peak, 1.0))
    return int(round(max(0.0, min(100.0, (db + 60) / 60 * 100))))


GAP_FILL_AFTER_S = 0.2  # no packets for this long = the system is silent
GAP_CHECK_S = 0.1


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
        gain: float = 1.0,
    ) -> None:
        self.device = device
        self.gain = gain
        self.last_peak = 0.0  # after gain; read by the level meter
        self.on_error = on_error or (lambda msg: None)
        start = time.monotonic()
        self.clock = clock or (lambda: time.monotonic() - start)
        self._on_audio: OnAudio | None = None
        self._resampler: Resampler | None = None
        self._failed = False
        self._lock = threading.Lock()
        self._audio_end: float | None = None  # session time where delivered audio ends
        self._gap_stop = threading.Event()
        self._gap_thread: threading.Thread | None = None

    def _deliver(self, block: np.ndarray, in_rate: int) -> None:
        if self._failed:
            return
        try:
            with self._lock:
                # Time of the block's first sample = now minus the block duration.
                duration = len(block) / in_rate
                t0 = self.clock() - duration
                self._audio_end = t0 + duration
                out = self._resampler.process(block)
                if self.gain != 1.0:
                    out = np.clip(out * self.gain, -1.0, 1.0).astype(np.float32, copy=False)
                if len(out):
                    self.last_peak = float(np.abs(out).max())
                if len(out) and self._on_audio:
                    self._on_audio(out, t0)
        except Exception as e:  # never let an exception escape the audio callback
            self._failed = True
            self._fail(e)

    def _fill_gap(self) -> None:
        """Deliver silence for the time no packets arrived (WASAPI loopback sends
        nothing while the system is quiet), so the segmenter can close the last
        utterance instead of waiting for the next sound."""
        with self._lock:
            if self._failed or self._audio_end is None or not self._on_audio:
                return
            gap = self.clock() - self._audio_end
            if gap < GAP_FILL_AFTER_S:
                return
            n = round(gap * TARGET_RATE)
            start = self._audio_end
            self._audio_end = start + n / TARGET_RATE
            self._on_audio(np.zeros(n, dtype=np.float32), start)

    def _start_gap_filler(self) -> None:
        def loop():
            while not self._gap_stop.wait(GAP_CHECK_S):
                try:
                    self._fill_gap()
                except Exception as e:
                    self._failed = True
                    self._fail(e)
                    return

        self._gap_stop.clear()
        self._gap_thread = threading.Thread(target=loop, daemon=True, name=f"{self.label}-gap")
        self._gap_thread.start()

    def _stop_gap_filler(self) -> None:
        self._gap_stop.set()
        if self._gap_thread:
            self._gap_thread.join(1.0)
            self._gap_thread = None

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
            self._start_gap_filler()
        except Exception as e:
            self._stream = None
            self._fail(e)

    def stop(self) -> None:
        self._stop_gap_filler()
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
