"""Claude Code (subscription) provider.

Runs the installed, unmodified `claude` CLI in headless mode with the user's
own sign-in. Each question gets its own process (so questions don't pile up
into one ever-growing conversation), and the next process is started in
advance so its start-up time is off the critical path.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Iterator

from shade.llm.base import ProviderError
from shade.models import Usage

ANSWER_TIMEOUT = 60.0  # max wait for the next chunk of an answer
DETECT_TIMEOUT = 20.0
NOT_SIGNED_IN = (
    "Claude Code: not signed in. Run `claude` in a terminal once and sign in with your Claude account."
)
LIMIT_REACHED = "Claude Code: subscription usage limit reached."

_FLAGS = [
    "-p",
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--verbose",
    "--include-partial-messages",
    "--tools", "",
    "--strict-mcp-config",
    "--setting-sources", "",
    "--no-session-persistence",
]


def find_claude(path: str = "") -> str | None:
    """The claude executable: the configured path, PATH, or the default install folder."""
    if path:
        return path if Path(path).is_file() else None
    found = shutil.which("claude")
    if found:
        return found
    default = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    return str(default) if default.is_file() else None


def _child_env() -> dict[str, str]:
    # Without ANTHROPIC_* the CLI uses the Claude account sign-in, not an API key
    # (a key may be in the environment for the Claude API provider).
    return {
        k: v for k, v in os.environ.items()
        if not k.startswith("ANTHROPIC_") and k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
    }


def _workdir() -> str:
    # An empty folder: no project CLAUDE.md or settings get picked up.
    d = Path(tempfile.gettempdir()) / "shade-claude-code"
    d.mkdir(exist_ok=True)
    return str(d)


def _map_result_error(text: str) -> ProviderError:
    low = text.lower()
    if "login" in low or "api key" in low or "authenticat" in low:
        return ProviderError(NOT_SIGNED_IN)
    if "limit" in low:
        return ProviderError(LIMIT_REACHED)
    return ProviderError(f"Claude Code: {text.strip()[:200]}")


class _Run:
    """One claude process and a thread that turns its stdout into events."""

    def __init__(self, args: list[str]) -> None:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=_workdir(),
                env=_child_env(),
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
        except OSError as e:
            raise ProviderError(f"Claude Code: cannot start ({e}).") from e
        self.events: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                pass
        self.events.put(None)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def send(self, content: list[dict]) -> None:
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.close()  # one question per process
        except OSError as e:
            raise ProviderError("Claude Code: the process stopped unexpectedly.") from e

    def kill(self) -> None:
        if self.alive():
            self.proc.kill()

    def stderr_tail(self) -> str:
        try:
            self.proc.wait(timeout=2)
            return (self.proc.stderr.read() or "").strip()[-200:]
        except Exception:
            return ""


class ClaudeCodeProvider:
    supports_images = True

    def __init__(self, model: str, detector_model: str, effort: str, command: list[str]) -> None:
        self.model = model
        self.detector_model = detector_model
        self.effort = effort
        self.last_usage = Usage()
        self._command = list(command)
        self._spares: dict[tuple[str, str, str], _Run] = {}
        self._lock = threading.Lock()
        self._closed = False

    # ---- processes ----------------------------------------------------------

    def _args(self, model: str, effort: str, system: str) -> list[str]:
        return [*self._command, *_FLAGS, "--model", model, "--effort", effort, "--system-prompt", system]

    def _take(self, model: str, effort: str, system: str) -> _Run:
        key = (model, effort, system)
        with self._lock:
            run = self._spares.pop(key, None)
        if run is None or not run.alive():
            run = _Run(self._args(model, effort, system))
        with self._lock:
            if not self._closed:
                try:
                    self._spares[key] = _Run(self._args(model, effort, system))  # for the next question
                except ProviderError:
                    pass
        return run

    def spare_pid(self, model: str, effort: str, system: str) -> int | None:
        run = self._spares.get((model, effort, system))
        return run.proc.pid if run else None

    def spare_processes(self) -> list[subprocess.Popen]:
        return [r.proc for r in self._spares.values()]

    def close(self) -> None:
        with self._lock:
            self._closed = True
            spares, self._spares = list(self._spares.values()), {}
        for run in spares:
            run.kill()

    # ---- requests -----------------------------------------------------------

    def _ask(
        self, model: str, effort: str, system: str, content: list[dict], cancel: threading.Event | None, timeout: float,
        record_usage: bool = False,
    ) -> Iterator[str]:
        run = self._take(model, effort, system)
        try:
            run.send(content)
            while True:
                try:
                    ev = run.events.get(timeout=timeout)
                except queue.Empty:
                    raise ProviderError("Claude Code: no answer (timed out).") from None
                if ev is None:
                    tail = run.stderr_tail()
                    raise ProviderError(f"Claude Code stopped without an answer. {tail}".strip())
                kind = ev.get("type")
                if kind == "stream_event":
                    e = ev.get("event", {})
                    d = e.get("delta", {})
                    if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                        yield d.get("text", "")
                        if cancel is not None and cancel.is_set():
                            return
                elif kind == "result":
                    if ev.get("is_error"):
                        raise _map_result_error(str(ev.get("result") or ev.get("subtype") or "error"))
                    u = ev.get("usage") or {}
                    if record_usage:  # detection must not overwrite an answer's usage
                        self.last_usage = Usage(
                            u.get("input_tokens") or 0,
                            u.get("output_tokens") or 0,
                            u.get("cache_read_input_tokens") or 0,
                        )
                    return
        finally:
            run.kill()

    def stream_answer(
        self, system: str, user_text: str, image_png: bytes | None, cancel: threading.Event
    ) -> Iterator[str]:
        content: list[dict] = []
        if image_png:
            data = base64.b64encode(image_png).decode("ascii")
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
        content.append({"type": "text", "text": user_text})
        self.last_usage = Usage()
        yield from self._ask(self.model, self.effort, system, content, cancel, ANSWER_TIMEOUT, record_usage=True)

    def detect(self, system: str, user_text: str) -> str:
        content = [{"type": "text", "text": user_text}]
        return "".join(self._ask(self.detector_model, "low", system, content, None, DETECT_TIMEOUT))
