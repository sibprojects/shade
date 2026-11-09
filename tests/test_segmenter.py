import numpy as np
import pytest

from shade.audio.segmenter import CHUNK, Segmenter

RATE = 16000
CHUNK_S = CHUNK / RATE


def scripted_prob(speech_ranges):
    """Fake VAD: probability by the chunk's start time."""
    state = {"i": 0}

    def prob(chunk):
        assert len(chunk) == CHUNK
        t = state["i"] * CHUNK_S
        state["i"] += 1
        return 0.9 if any(a <= t < b for a, b in speech_ranges) else 0.1

    return prob


def run(speech_ranges, total_s, block=CHUNK, **kw):
    out = []
    seg = Segmenter(
        "them", scripted_prob(speech_ranges), lambda *a: out.append(a), **kw
    )
    samples = np.zeros(int(total_s * RATE), dtype=np.float32)
    for i in range(0, len(samples), block):
        seg.feed(samples[i : i + block], i / RATE)
    return out


def test_one_utterance_with_pre_roll():
    out = run([(0.5, 1.5)], 2.2)
    assert len(out) == 1
    source, audio, start, end = out[0]
    assert source == "them"
    assert start == pytest.approx(0.3, abs=0.05)
    assert end == pytest.approx(1.5, abs=0.05)
    assert len(audio) == pytest.approx((end - start) * RATE, abs=CHUNK)


def test_short_blip_dropped():
    assert run([(0.5, 0.6)], 1.5) == []


def test_long_speech_forced_at_max():
    out = run([(0.0, 25.0)], 25.0)
    assert out[0][3] == pytest.approx(20.0, abs=0.05)


def test_odd_block_size_same_result():
    a = run([(0.5, 1.5)], 2.2)
    b = run([(0.5, 1.5)], 2.2, block=333)
    assert len(a) == len(b) == 1
    assert b[0][2] == pytest.approx(a[0][2], abs=1e-6)
    assert b[0][3] == pytest.approx(a[0][3], abs=1e-6)
    assert len(b[0][1]) == len(a[0][1])


def test_no_emit_before_enough_silence():
    assert run([(0.5, 1.5)], 1.9) == []
