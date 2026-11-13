import numpy as np
import pytest

from shade.audio.resample import Resampler
from shade.audio.vad import SileroVad


def test_resample_48k_stereo_to_16k_mono():
    r = Resampler(48000, 2)
    t = np.arange(48000) / 48000
    tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    stereo = np.stack([tone, tone], axis=1)
    out = [r.process(stereo[i : i + 4800]) for i in range(0, 48000, 4800)]
    joined = np.concatenate(out)
    assert joined.dtype == np.float32
    assert joined.ndim == 1
    # soxr keeps ~20 ms in its filter until more input arrives
    assert len(joined) == pytest.approx(16000, abs=400)


def test_resample_passthrough_16k_mono():
    r = Resampler(16000, 1)
    block = np.ones(1600, dtype=np.float32)
    assert np.array_equal(r.process(block), block)


def test_silero_silence_is_not_speech():
    vad = SileroVad()
    probs = [vad(np.zeros(512, dtype=np.float32)) for _ in range(10)]
    assert all(0.0 <= p < 0.5 for p in probs)
