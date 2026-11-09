"""Crash-safe session files: every write is appended and flushed immediately."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path

from shade.models import HintRequest, Usage, Utterance
from shade.transcript import format_lines


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "session"


def _stamp(req: HintRequest) -> str:
    t = int(req.context[-1].end) if req.context else 0
    m, s = divmod(t, 60)
    return f"{m:02d}:{s:02d}"


class SessionWriter:
    def __init__(self, root: Path, profile_name: str, started: datetime) -> None:
        self.dir = Path(root) / f"{started:%Y-%m-%d_%H-%M}_{slug(profile_name)}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        when = f"{started:%Y-%m-%d %H:%M}"
        self._transcript = open(self.dir / "transcript.md", "a", encoding="utf-8")
        self._hints = open(self.dir / "hints.md", "a", encoding="utf-8")
        self._write(self._transcript, f"# Transcript — {profile_name} — {when}\n\n")
        self._write(self._hints, f"# Hints — {profile_name} — {when}\n\n")

    def _write(self, f, text: str) -> None:
        with self._lock:
            f.write(text)
            f.flush()

    def write_utterance(self, u: Utterance) -> None:
        self._write(self._transcript, format_lines([u]) + "\n")

    def _heading(self, req: HintRequest, model: str | None) -> str:
        head = f"## [{_stamp(req)}] #{req.id} ({req.trigger})"
        if model:
            head += f" — {model}"
        return head + "\n" + f"**Q:** {req.question}\n"

    def write_hint(
        self,
        req: HintRequest,
        answer: str,
        model: str,
        usage: Usage,
        cost: float,
        total_cost: float,
    ) -> None:
        parts = [self._heading(req, model)]
        if req.image_png:
            (self.dir / f"hint-{req.id}.png").write_bytes(req.image_png)
            parts.append(f"![screenshot](hint-{req.id}.png)\n")
        parts.append(answer.rstrip() + "\n")
        parts.append(
            f"_tokens in/out: {usage.input_tokens}/{usage.output_tokens} · "
            f"cost: ${cost:.4f} · session total: ${total_cost:.4f}_\n\n"
        )
        self._write(self._hints, "".join(parts))

    def write_error(self, req: HintRequest, message: str) -> None:
        self._write(self._hints, self._heading(req, None) + f"**Error:** {message}\n\n")

    def close(self) -> None:
        with self._lock:
            self._transcript.close()
            self._hints.close()
