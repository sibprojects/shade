"""Core data types shared by the engine, providers, session files and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

Source = Literal["me", "them"]
Trigger = Literal["auto", "hotkey", "screenshot"]


@dataclass(frozen=True)
class Utterance:
    source: Source
    text: str
    start: float  # seconds since session start
    end: float


@dataclass
class HintRequest:
    id: int
    trigger: Trigger
    question: str
    context: list[Utterance]
    image_png: bytes | None = None
    # Earlier (question, answer) pairs of this call, oldest first, for follow-ups.
    previous: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class UtteranceAdded:
    u: Utterance


@dataclass
class HintStarted:
    id: int
    trigger: Trigger
    question: str


@dataclass
class HintDelta:
    id: int
    text: str


@dataclass
class HintDone:
    id: int
    model: str
    usage: Usage
    cost: float
    total_cost: float


@dataclass
class HintError:
    id: int
    message: str


@dataclass
class Status:
    message: str


Event = Union[UtteranceAdded, HintStarted, HintDelta, HintDone, HintError, Status]
