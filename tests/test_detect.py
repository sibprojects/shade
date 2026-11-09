from shade.detect import Detector
from shade.llm.base import ProviderError
from shade.models import Utterance
from shade.prompt import DETECT_RULES


class FakeProvider:
    def __init__(self, reply="NONE", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def detect(self, system, user_text):
        self.calls.append((system, user_text))
        if self.error:
            raise self.error
        return self.reply


def test_me_utterance_not_checked():
    p = FakeProvider()
    assert Detector(p).check(Utterance("me", "How would you design the cache?", 0, 1), []) is None
    assert p.calls == []


def test_short_utterance_not_checked():
    p = FakeProvider()
    assert Detector(p).check(Utterance("them", "Okay sure", 0, 1), []) is None
    assert p.calls == []


def test_question_detected():
    p = FakeProvider("ASK: How would you design the cache?")
    latest = Utterance("them", "How would you design the cache?", 0, 1)
    assert Detector(p).check(latest, [latest]) == "How would you design the cache?"
    assert p.calls[0][0] == DETECT_RULES
    assert p.calls[0][1].endswith("Latest utterance from Them:\nHow would you design the cache?")


def test_provider_error_returns_none():
    p = FakeProvider(error=ProviderError("down"))
    assert Detector(p).check(Utterance("them", "How do you deploy it?", 0, 1), []) is None
