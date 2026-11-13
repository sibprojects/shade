"""Prompt texts and builders for answering and question detection."""

from __future__ import annotations

from shade.models import HintRequest, Utterance
from shade.transcript import format_lines

ANSWER_RULES = """\
You are a real-time assistant helping the user during a live call. The user reads your answer while talking, so be fast and brief.
Format:
1. First, 1-3 short lines the user can say out loud right away, in first person, natural spoken English.
2. Then, only if useful, up to 4 short bullet points with supporting details.
3. If the task needs code, put it in a single fenced code block after the bullets, labeled with its language (```python, ```php, ```go, ...).
Never add preambles, apologies or meta commentary. English only.
The user's profile and the context of this call follow."""

DETECT_RULES = """\
You watch a live call transcript. Decide whether the other side's latest utterance contains a question or a task/request directed at the user, including indirect ones like "walk us through..." or "how would you handle...". Small talk, greetings and plain statements are not.
Reply with exactly one line: either NONE, or ASK: <the question or task rewritten as one self-contained sentence>."""

SCREENSHOT_TASK = "Solve or answer the task shown in the screenshot."
PREVIOUS_CHARS = 2000  # per earlier answer sent along with a follow-up


def build_system(profile_text: str) -> str:
    return ANSWER_RULES + "\n\n---\n\n" + profile_text.strip()


def build_user_text(req: HintRequest) -> str:
    question = req.question
    if req.trigger == "screenshot" and not question.strip():
        question = SCREENSHOT_TASK
    earlier = ""
    if req.previous:
        pairs = "\n\n".join(f"Q: {q}\nA: {a[:PREVIOUS_CHARS]}" for q, a in req.previous)
        earlier = (
            "Your earlier answers in this call (the new question may follow up on them; "
            "build on them instead of starting over):\n" + pairs + "\n\n"
        )
    return earlier + "Recent conversation:\n" + format_lines(req.context) + "\n\nAnswer this now:\n" + question


def build_detect_text(recent: list[Utterance], latest: Utterance) -> str:
    return format_lines(recent) + "\n\nLatest utterance from Them:\n" + latest.text


def parse_detection(text: str) -> str | None:
    t = text.strip()
    if not t[:4].upper() == "ASK:":
        return None
    rest = t[4:].strip()
    return rest or None
