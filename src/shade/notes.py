"""Call notes written after a session from its transcript and hints."""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable

from shade.llm.base import Provider

NOTES_FILE = "notes.md"
MAX_TRANSCRIPT_CHARS = 120_000  # about two hours of talk; the end is kept
MAX_HINTS_CHARS = 30_000
_SPEECH_LINE = re.compile(r"^\[\d+:\d\d\] (Me|Them): ", re.MULTILINE)

NOTES_RULES = """\
You write short notes after a call, for the user ("Me" in the transcript; "Them" is the other side).
The hints are answers an assistant suggested to the user during the call; the user may or may not have used them.
Use only what is in the transcript. Never invent facts, names or numbers. English only.

Output only Markdown with exactly these sections:

# Call notes

## Summary
3-5 bullets: what the call was about and how it went.

## Questions
For each real question or task from Them, in order:
- **<the question, short>** - what I answered, in a few words, and how well (good / partial / missed).
  If partial or missed: one line with a better answer.

## To do
Anything I promised or was asked to do, and next steps that were mentioned. "- Nothing mentioned." if none.

## Follow-up email
A short, friendly email I can send after the call: thanks, one or two points from the call, next step.
No subject line, no placeholders except [Name].
"""


def _tail(text: str, limit: int) -> str:
    return text if len(text) <= limit else "…\n" + text[-limit:]


def has_speech(session_dir: Path) -> bool:
    path = Path(session_dir) / "transcript.md"
    return path.is_file() and bool(_SPEECH_LINE.search(path.read_text(encoding="utf-8", errors="replace")))


def build_notes_request(session_dir: Path) -> str:
    d = Path(session_dir)
    transcript = (d / "transcript.md").read_text(encoding="utf-8", errors="replace")
    hints_path = d / "hints.md"
    hints = hints_path.read_text(encoding="utf-8", errors="replace") if hints_path.is_file() else ""
    return (
        "Transcript:\n" + _tail(transcript.strip(), MAX_TRANSCRIPT_CHARS)
        + "\n\nHints shown to me during the call:\n" + (_tail(hints.strip(), MAX_HINTS_CHARS) or "(none)")
        + "\n\nWrite the call notes now."
    )


def make_notes(provider: Provider, session_dir: Path, cancel: threading.Event) -> Path:
    """Write notes.md into the session folder and return its path."""
    if not has_speech(session_dir):
        raise ValueError("Nothing to summarize: the session has no transcript.")
    parts = list(provider.stream_answer(NOTES_RULES, build_notes_request(session_dir), None, cancel))
    path = Path(session_dir) / NOTES_FILE
    path.write_text("".join(parts).strip() + "\n", encoding="utf-8", newline="\n")
    return path


def latest_session(sessions_dir: Path) -> Path | None:
    """The newest session folder (names start with the date and time)."""
    root = Path(sessions_dir)
    if not root.is_dir():
        return None
    found = sorted(d for d in root.iterdir() if (d / "transcript.md").is_file())
    return found[-1] if found else None


def start_notes(
    provider_factory: Callable[[], Provider],
    session_dir: Path,
    on_done: Callable[[Path], None],
    on_error: Callable[[str], None],
) -> threading.Thread:
    """Write the notes on a background thread; exactly one callback is called."""

    def work():
        provider = None
        try:
            provider = provider_factory()
            on_done(make_notes(provider, session_dir, threading.Event()))
        except Exception as e:  # provider, file or anything else: never die silently
            on_error(f"Call notes failed: {e}")
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                close()

    t = threading.Thread(target=work, daemon=True, name="notes")
    t.start()
    return t
