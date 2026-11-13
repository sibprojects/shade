import pytest

from shade.detect import RuleDetector
from shade.models import Utterance
from shade.rules import looks_like_question

QUESTIONS = [
    "How would you design a cache for a service that gets ten thousand requests per second?",
    "What's the difference between a process and a thread",
    "Could you start by telling me a bit about yourself",
    "Tell me about a project you're most proud of.",
    "Walk me through how you would design a URL shortener.",
    "So, explain eventual consistency in simple terms.",
    "I'm curious how you handled scaling at your last job.",
    "I'd like to understand your experience with Kafka.",
    "Let's say you have a table with a billion rows and a query is slow.",
    "Imagine the database goes down in the middle of the night.",
    "Write a function that checks whether a string is a palindrome.",
    "Find the second largest number in an array without sorting it.",
    "And what about writes?",
    "Do you have any experience with Kubernetes",
    "Have you ever heard of hang gliding?",
    "How long ago was it though",
    "I don't know if you've been to Sweden.",
    "Okay, what from eating too much sugar?",
    "Was it cool?",
    "Did you get?",
]

NOT_QUESTIONS = [
    "when I was working my last job.",
    "when i was on a night out yeah and i have these two front teeth",
    "Thanks for joining, can you hear me okay?",
    "Is my screen visible?",
    "Yeah, how are you doing? You good?",
    "Our main product is a booking platform for hotels.",
    "Okay, that makes sense.",
    "Let me share my screen for a second.",
    "So the second question is about concurrency.",
    "which I think I think that I've been",
    "Ah, really? Wow.",
    "Yeah, fair enough.",
]


@pytest.mark.parametrize("text", QUESTIONS)
def test_questions_and_tasks_are_found(text):
    assert looks_like_question(text)


@pytest.mark.parametrize("text", NOT_QUESTIONS)
def test_statements_and_small_talk_are_not(text):
    assert not looks_like_question(text)


def _u(src, text):
    return Utterance(src, text, 0.0, 1.0)


def test_rule_detector_returns_the_question_without_any_model():
    d = RuleDetector()
    assert d.check(_u("them", "How would you scale the reads?"), []) == "How would you scale the reads?"
    assert d.check(_u("them", "Our stack is Go and React."), []) is None


def test_rule_detector_ignores_own_speech_and_short_lines():
    d = RuleDetector()
    assert d.check(_u("me", "How would I do that?"), []) is None
    assert d.check(_u("them", "Why?"), []) is None


def test_subscription_finds_questions_by_rules_and_allows_auto_by_default():
    from shade.config import Settings, auto_allowed, detection_by_rules
    assert detection_by_rules(Settings(provider="claude_code"))
    assert not detection_by_rules(Settings())
    assert not detection_by_rules(Settings(provider="openai"))
    assert auto_allowed(Settings(provider="claude_code"))  # detection is free now
    assert not auto_allowed(Settings(provider="claude_code", cc_auto=False))
