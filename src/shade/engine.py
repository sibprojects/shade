"""Orchestrates transcript, detection and hint generation.

All work happens on worker threads; results are reported through on_event.
Cancel/replace policy:
- a hotkey or screenshot hint cancels any running hint;
- an auto hint cancels a running auto hint, but is dropped while a hotkey or
  screenshot hint is running.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from shade.cost import CostMeter
from shade.detect import Detector
from shade.llm.base import Provider, ProviderError
from shade.models import (
    Event,
    HintDelta,
    HintDone,
    HintError,
    HintRequest,
    HintStarted,
    Status,
    Trigger,
    Utterance,
    UtteranceAdded,
)
from shade.prompt import SCREENSHOT_TASK, build_system, build_user_text
from shade.session import SessionWriter
from shade.transcript import Transcript

NO_VISION = "Selected local model does not support images."
# A queued detection older than this is skipped: its hint would arrive too late.
STALE_DETECT_S = 10.0
STOP_JOIN_S = 2.0
MAX_PREVIOUS = 3  # earlier answers sent along, so follow-up questions build on them


@dataclass
class _Run:
    req: HintRequest
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class Engine:
    def __init__(
        self,
        provider: Provider,
        detector: Detector,
        transcript: Transcript,
        writer: SessionWriter,
        cost: CostMeter,
        profile_text: str,
        context_seconds: float,
        on_event: Callable[[Event], None],
        clock: Callable[[], float],
    ) -> None:
        self.provider = provider
        self.detector = detector
        self.transcript = transcript
        self.writer = writer
        self.cost = cost
        self.system = build_system(profile_text)
        self.context_seconds = context_seconds
        self.on_event = on_event
        self.clock = clock
        self.auto_enabled = True
        self._stopped = False
        self._lock = threading.Lock()
        self._next_id = 0
        self._current: _Run | None = None
        self._runs: list[_Run] = []
        self._exchanges: list[tuple[str, str]] = []  # finished (question, answer) pairs
        self._detect_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="detect")

    # ---- inputs -------------------------------------------------------

    def on_utterance(self, u: Utterance) -> None:
        self.transcript.add(u)
        self.writer.write_utterance(u)
        self.on_event(UtteranceAdded(u))
        if self.auto_enabled and u.source == "them":
            self._detect_pool.submit(self._guard, self._detect, u)

    def ask_now(self) -> None:
        question = self.transcript.last_question()
        if question is None:
            self.on_event(Status("No question yet."))
            return
        self._start("hotkey", question, None)

    def ask_with_image(self, png: bytes) -> None:
        if not self.provider.supports_images:
            with self._lock:
                self._next_id += 1
                hint_id = self._next_id
            self.on_event(HintError(hint_id, NO_VISION))
            return
        self._start("screenshot", self.transcript.last_question() or "", png)

    def new_topic(self) -> None:
        """Forget earlier answers: the next question starts from scratch."""
        with self._lock:
            self._exchanges.clear()

    def set_auto(self, enabled: bool) -> None:
        self.auto_enabled = enabled

    # ---- lifecycle ----------------------------------------------------

    def wait_idle(self, timeout: float) -> bool:
        """Wait until queued detections and running hints finish (for tests)."""
        try:
            self._detect_pool.submit(lambda: None).result(timeout)
        except Exception:
            return False
        with self._lock:
            runs = list(self._runs)
        for run in runs:
            if run.thread:
                run.thread.join(timeout)
                if run.thread.is_alive():
                    return False
        return True

    def stop(self) -> None:
        """Stop accepting work, cancel the running hint and give it a moment to
        save its partial answer before the caller closes the session files."""
        with self._lock:
            self._stopped = True
            runs = [r for r in self._runs if r.alive()]
            for r in runs:
                r.cancel.set()
        self._detect_pool.shutdown(wait=False, cancel_futures=True)
        deadline = time.monotonic() + STOP_JOIN_S
        for r in runs:
            r.thread.join(max(0.0, deadline - time.monotonic()))

    # ---- internals ----------------------------------------------------

    def _guard(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as e:  # never let a worker thread die silently
            self.on_event(Status(f"Internal error: {e}"))

    def _detect(self, u: Utterance) -> None:
        if self._stopped or self.clock() - u.end > STALE_DETECT_S:
            return
        recent = self.transcript.window(self.clock(), self.context_seconds)
        question = self.detector.check(u, recent)
        if question and self.auto_enabled:
            self._start("auto", question, None)

    def _start(self, trigger: Trigger, question: str, image: bytes | None) -> None:
        with self._lock:
            if self._stopped:
                return
            cur = self._current
            if cur and cur.alive() and not cur.cancel.is_set():
                if trigger == "auto" and cur.req.trigger != "auto":
                    return
                cur.cancel.set()
            self._next_id += 1
            context = self.transcript.window(self.clock(), self.context_seconds)
            previous = list(self._exchanges[-MAX_PREVIOUS:])
            run = _Run(HintRequest(self._next_id, trigger, question, context, image, previous))
            run.thread = threading.Thread(
                target=self._guard, args=(self._run_hint, run), daemon=True,
                name=f"hint-{self._next_id}",
            )
            self._current = run
            self._runs = [r for r in self._runs if r.alive()] + [run]
            self.on_event(HintStarted(run.req.id, trigger, question))
            run.thread.start()

    def _run_hint(self, run: _Run) -> None:
        req = run.req
        parts: list[str] = []
        try:
            stream = self.provider.stream_answer(
                self.system, build_user_text(req), req.image_png, run.cancel
            )
            for text in stream:
                if run.cancel.is_set():
                    break
                parts.append(text)
                self.on_event(HintDelta(req.id, text))
        except ProviderError as e:
            self.writer.write_error(req, str(e))
            self.on_event(HintError(req.id, str(e)))
            return
        answer = "".join(parts)
        if run.cancel.is_set():
            answer += " _(cancelled)_"
        elif answer.strip():
            with self._lock:
                self._exchanges.append((req.question or SCREENSHOT_TASK, answer))
                del self._exchanges[:-MAX_PREVIOUS]
        usage = self.provider.last_usage
        cost = self.cost.add(self.provider.model, usage)
        self.writer.write_hint(req, answer, self.provider.model, usage, cost, self.cost.total)
        self.on_event(HintDone(req.id, self.provider.model, usage, cost, self.cost.total))
