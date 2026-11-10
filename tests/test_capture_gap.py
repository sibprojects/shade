"""WASAPI loopback sends no packets while nothing plays; Shade must still see the
silence, or the last utterance before a pause is never closed."""

import numpy as np
import pytest

from shade.audio.capture import LoopbackSource
from shade.audio.resample import Resampler


def _source(now):
    got = []
    src = LoopbackSource(clock=lambda: now[0])
    src._resampler = Resampler(16000, 1)
    src._on_audio = lambda a, t: got.append((len(a), round(t, 3), float(np.abs(a).max())))
    return src, got


def test_gap_after_audio_is_filled_with_silence():
    now = [1.0]
    src, got = _source(now)
    src._deliver(np.ones(8000, dtype=np.float32), 16000)  # 0.5 s ending at t=1.0
    now[0] = 1.5
    src._fill_gap()
    assert got[-1] == (8000, 1.0, 0.0)


def test_no_fill_while_packets_keep_coming():
    now = [1.0]
    src, got = _source(now)
    src._deliver(np.ones(1600, dtype=np.float32), 16000)
    now[0] = 1.05  # 50 ms later: within the normal packet interval
    src._fill_gap()
    assert len(got) == 1


def test_no_fill_before_any_audio():
    now = [5.0]
    src, got = _source(now)
    src._fill_gap()
    assert got == []


def test_fill_is_continuous_across_calls():
    now = [1.0]
    src, got = _source(now)
    src._deliver(np.ones(1600, dtype=np.float32), 16000)
    now[0] = 1.3
    src._fill_gap()
    now[0] = 1.6
    src._fill_gap()
    assert [(n, t) for n, t, _ in got[1:]] == [(4800, 1.0), (4800, 1.3)]
    assert sum(n for n, _, _ in got[1:]) == pytest.approx(9600)
