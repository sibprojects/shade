import numpy as np
import pytest

from shade.audio.segmenter import CHUNK, Segmenter
from shade.config import Settings
from shade.models import Utterance
from shade.stt import SttWorker, build_stt_prompt

PROFILE = """# Profile

## About me
- Teacher.

## This call
- Type: interview.
- Topic: math questions — derivatives, integrals, probability.

## How to answer
- Short.
"""


def test_default_speech_model_is_turbo():
    assert Settings().stt_model == "large-v3-turbo"


def test_prompt_has_call_topic_and_recent_lines():
    recent = [Utterance("them", "Let's start.", 0, 1), Utterance("me", "Sure.", 1, 2), Utterance("them", "Integrate x squared.", 3, 4)]
    p = build_stt_prompt(PROFILE, recent)
    assert "derivatives, integrals, probability" in p
    assert p.endswith("Sure. Integrate x squared.")
    assert "Let's start." not in p  # only the last two lines


def test_prompt_is_bounded():
    long = [Utterance("them", "word " * 400, 0, 1)]
    assert len(build_stt_prompt(PROFILE * 20, long)) <= 600


def test_prompt_empty_without_profile_or_history():
    assert build_stt_prompt("", []) is None


def test_worker_passes_prompt_to_transcriber():
    seen = []

    class T:
        def transcribe(self, audio, prompt=None):
            seen.append(prompt)
            return "Hello there friend"

    w = SttWorker(T(), lambda u: None, prompt_fn=lambda: "ctx")
    w.submit("them", np.zeros(10, dtype=np.float32), 0, 1)
    w.stop()
    assert seen == ["ctx"]


def test_segmenter_keeps_a_short_tail_after_the_last_word():
    out = []
    state = {"i": 0}

    def prob(chunk):
        t = state["i"] * CHUNK / 16000
        state["i"] += 1
        return 0.9 if 0.5 <= t < 1.5 else 0.1

    seg = Segmenter("them", prob, lambda *a: out.append(a))
    samples = np.zeros(int(2.5 * 16000), dtype=np.float32)
    for i in range(0, len(samples), CHUNK):
        seg.feed(samples[i : i + CHUNK], i / 16000)
    _, audio, start, end = out[0]
    assert end == pytest.approx(1.7, abs=0.05)  # 0.2 s tail kept after the speech
