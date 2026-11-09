import numpy as np
import pytest

from shade.models import Utterance
from shade.stt import SttWorker, is_junk


@pytest.mark.parametrize("text", ["", "   ", " Thank you. ", "...", "You", "Thanks for watching!", "um"])
def test_junk(text):
    assert is_junk(text)


@pytest.mark.parametrize("text", ["Thank you for the question, so", "Why?", "You know what"])
def test_not_junk(text):
    assert not is_junk(text)


class FakeTranscriber:
    def __init__(self, replies):
        self.replies = list(replies)

    def transcribe(self, audio):
        return self.replies.pop(0)


def test_worker_drops_junk_and_keeps_source_and_times():
    got = []
    w = SttWorker(FakeTranscriber(["Thank you.", " Real text "]), got.append)
    w.submit("them", np.zeros(16000, dtype=np.float32), 1.0, 2.0)
    w.submit("me", np.zeros(16000, dtype=np.float32), 3.0, 4.0)
    w.stop()
    assert got == [Utterance("me", "Real text", 3.0, 4.0)]


def test_worker_survives_transcriber_error():
    class Boom:
        calls = 0

        def transcribe(self, audio):
            Boom.calls += 1
            if Boom.calls == 1:
                raise RuntimeError("cuda")
            return "After error"

    got, errors = [], []
    w = SttWorker(Boom(), got.append, on_error=errors.append)
    w.submit("them", np.zeros(10, dtype=np.float32), 0.0, 1.0)
    w.submit("them", np.zeros(10, dtype=np.float32), 1.0, 2.0)
    w.stop()
    assert errors == ["Speech recognition error: cuda"]
    assert got == [Utterance("them", "After error", 1.0, 2.0)]
