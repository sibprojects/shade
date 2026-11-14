"""Rolling transcript of the call."""

from __future__ import annotations

import bisect
import threading

from shade.models import Utterance

_LABELS = {"me": "Me", "them": "Them", "note": "Note"}


def joins(prev_source: str | None, u: Utterance) -> bool:
    """Like live captions: a speaker's phrases join one line until the other
    side speaks. Typed notes always get their own line."""
    return u.source == prev_source and u.source != "note"


def line_start(u: Utterance) -> str:
    m, s = divmod(int(u.start), 60)
    return f"[{m:02d}:{s:02d}] {_LABELS[u.source]}: {u.text}"


def format_lines(utts: list[Utterance]) -> str:
    lines: list[str] = []
    prev: str | None = None
    for u in utts:
        if lines and joins(prev, u):
            lines[-1] += " " + u.text
        else:
            lines.append(line_start(u))
        prev = u.source
    return "\n".join(lines)


class Transcript:
    def __init__(self) -> None:
        self._items: list[Utterance] = []
        self._lock = threading.Lock()

    def add(self, u: Utterance) -> None:
        with self._lock:
            keys = [x.end for x in self._items]
            self._items.insert(bisect.bisect_right(keys, u.end), u)

    def all(self) -> list[Utterance]:
        with self._lock:
            return list(self._items)

    def window(self, now: float, seconds: float) -> list[Utterance]:
        with self._lock:
            return [u for u in self._items if u.end >= now - seconds]

    def last_question(self) -> str | None:
        with self._lock:
            parts: list[str] = []
            for u in reversed(self._items):
                if u.source == "them":
                    parts.append(u.text)
                elif parts:
                    break  # the run of "them" before the user's own reply
        if not parts:
            return None
        return " ".join(reversed(parts))
