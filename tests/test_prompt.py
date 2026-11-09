from shade.models import HintRequest, Utterance
from shade.prompt import (
    ANSWER_RULES,
    build_detect_text,
    build_system,
    build_user_text,
    parse_detection,
)


def test_parse_detection_ask():
    assert parse_detection("ASK: How would you scale it?") == "How would you scale it?"


def test_parse_detection_none():
    assert parse_detection("NONE") is None


def test_parse_detection_empty_ask():
    assert parse_detection("ask:   ") is None


def test_parse_detection_requires_prefix_at_start():
    assert parse_detection("Sure, ASK: x") is None


def test_build_system_appends_profile():
    s = build_system("  I am a Python dev \n")
    assert s.startswith(ANSWER_RULES)
    assert s.endswith("---\n\nI am a Python dev")


def test_build_user_text_has_context_and_question():
    req = HintRequest(1, "hotkey", "Why Rust?", [Utterance("them", "Why Rust?", 61, 62)])
    text = build_user_text(req)
    assert text == "Recent conversation:\n[01:01] Them: Why Rust?\n\nAnswer this now:\nWhy Rust?"


def test_screenshot_without_question_uses_default_task():
    req = HintRequest(2, "screenshot", "", [], b"png")
    assert build_user_text(req).endswith(
        "Answer this now:\nSolve or answer the task shown in the screenshot."
    )


def test_build_detect_text():
    recent = [Utterance("me", "Hello", 0, 1)]
    latest = Utterance("them", "How do you test it?", 2, 3)
    assert build_detect_text(recent, latest) == (
        "[00:00] Me: Hello\n\nLatest utterance from Them:\nHow do you test it?"
    )
