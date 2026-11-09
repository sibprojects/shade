from shade.models import Utterance
from shade.transcript import Transcript, format_lines


def _u(source, text, start, end):
    return Utterance(source, text, start, end)


def test_window_limits_by_time():
    t = Transcript()
    t.add(_u("them", "old", 5, 10))
    t.add(_u("them", "mid", 195, 200))
    t.add(_u("them", "new", 385, 390))
    assert [u.text for u in t.window(now=400, seconds=180)] == ["new"]


def test_last_question_joins_trailing_them():
    t = Transcript()
    t.add(_u("me", "hi", 0, 1))
    t.add(_u("them", "So tell me", 2, 3))
    t.add(_u("them", "about your last project", 3, 5))
    assert t.last_question() == "So tell me about your last project"


def test_last_question_none_after_me():
    t = Transcript()
    t.add(_u("them", "q?", 0, 1))
    t.add(_u("me", "answer", 2, 3))
    assert t.last_question() is None


def test_last_question_none_when_empty():
    assert Transcript().last_question() is None


def test_add_keeps_order_by_end():
    t = Transcript()
    t.add(_u("them", "second", 3, 6))
    t.add(_u("me", "first", 1, 4))
    assert [u.text for u in t.all()] == ["first", "second"]


def test_format_lines():
    lines = format_lines([_u("them", "Why?", 187.2, 188.0), _u("me", "Because.", 189.0, 190.0)])
    assert lines == "[03:07] Them: Why?\n[03:09] Me: Because."
