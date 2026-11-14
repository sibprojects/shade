"""Create a call profile (.md) from a CV and a job description with the answer model."""

from __future__ import annotations

import re
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Callable

from shade.llm.base import Provider
from shade.session import slug

PROFILE_RULES = """\
You write a call profile for Shade, an assistant that suggests answers to the user during a live call in English.
The profile becomes the system prompt for every answer, so it must be short, factual and in English.
Use only facts from the CV and the job description. Never invent projects, numbers or skills.
Write in first person where it fits ("I built...").

Output only the Markdown profile, nothing before or after it, with exactly these sections:

# <Role> interview

## About me
- 8-12 bullets: seniority and years, main stack, databases, architecture, infrastructure, testing, domains, spoken languages.
- One bullet: "If asked about something I have not used, say so honestly and explain how I would approach it."

## Experience
- One bullet per job, newest first: **Company (dates), title.** One line on the product and stack.
  - 2-4 sub-bullets with concrete results from the CV.

## This call
- Terms: <comma-separated technologies, product names and jargon likely to be spoken in this call, for the speech recognizer>
- Type: <e.g. technical interview>
- Audience: <who is on the call, if known; otherwise "interviewers">
- Topic: <what the call is about, then the likely question areas based on the job description>

## How to answer
- Short answers: the main point first, then 2-3 bullet points.
- Simple English with short sentences that are easy to say out loud.
- Use my real experience from above when it fits.
- 2-4 more bullets specific to this role (e.g. code language and style, system design structure).

## Gaps
- Requirements from the job description that the CV does not show, one per bullet, each with a short honest angle
  (related experience, or how I would learn it). Write "- None found." if there are none.
"""

MAX_DOC_CHARS = 30_000  # per document sent to the model


def build_profile_request(cv: str, job: str, notes: str) -> str:
    parts = ["My CV:\n" + cv.strip()[:MAX_DOC_CHARS]]
    if job.strip():
        parts.append("Job description:\n" + job.strip()[:MAX_DOC_CHARS])
    else:
        parts.append("No job description: infer the likely topics from the CV.")
    if notes.strip():
        parts.append("About this call:\n" + notes.strip())
    parts.append("Write the profile now.")
    return "\n\n".join(parts)


def clean_profile(text: str) -> str:
    """Drop a wrapping code fence and anything the model wrote before the title."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines = lines[i:]
            break
    return "\n".join(lines).strip() + "\n"


def generate_profile(
    provider: Provider,
    cv: str,
    job: str,
    notes: str,
    cancel: threading.Event,
    on_delta: Callable[[str], None] | None = None,
) -> str:
    if not cv.strip():
        raise ValueError("Add your CV first.")
    parts: list[str] = []
    for text in provider.stream_answer(PROFILE_RULES, build_profile_request(cv, job, notes), None, cancel):
        if cancel.is_set():
            break
        parts.append(text)
        if on_delta:
            on_delta(text)
    return clean_profile("".join(parts))


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paragraphs = ["".join(t.text or "" for t in p.iter(f"{_W}t")) for p in root.iter(f"{_W}p")]
    return "\n".join(p for p in paragraphs if p.strip())


def read_document(path: Path) -> str:
    """Text of a CV or job description: .docx, or any text file (UTF-8 or Windows-1251)."""
    path = Path(path)
    if path.suffix.lower() == ".docx":
        return _read_docx(path)
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def profile_path(folder: Path, name: str) -> Path:
    """A new file in the profiles folder; never overwrites an existing profile."""
    base = re.sub(r"-+", "-", slug(name))
    path = Path(folder) / f"{base}.md"
    n = 2
    while path.exists():
        path = Path(folder) / f"{base}-{n}.md"
        n += 1
    return path
