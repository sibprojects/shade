"""Finding questions and tasks by rules, without a model.

Measured on a real one-hour call plus interview-style lines: about as many
questions found as a small model, with far fewer false alarms, in no time.
Used with Claude Code (subscription) so detection doesn't spend the plan.
"""

from __future__ import annotations

import re

_FILLERS = re.compile(
    r"^(so|okay|ok|and|but|well|yeah|yes|right|alright|all right|um|uh|erm|ah|oh|like|great|cool|now|then|thanks)"
    r"[\s,.!-]+"
)
# Checks and greetings that end with "?" but need no hint.
_SMALL_TALK = re.compile(
    r"\b(can you (hear|see) (me|my|it|that|this)|hear me|is my screen|see my screen|screen visible|"
    r"how are you|how's it going|how is it going|you good\b|are you there)"
)
# Short reactions like "Really? Wow." or "Seriously?"
_REACTION = re.compile(r"^(really|seriously|wow|huh|no way)\b[?!.,\s]*\w*[?!.]*$")
_AUX = r"(can|could|would|will|do|does|did|have|has|had|is|are|was|were|should|shall|may|might|must)"
_SUBJECT = r"(you|we|i|it|there|they|he|she|that|this|your|these|those|anyone|anybody)"
_WH = r"(what|why|how|when|where|which|who|whose|whom)"
# A question word counts only when a question follows: "when would you…", not "when I was…".
_WH_QUESTION = re.compile(
    rf"^{_WH}('s|'re|'d|\s+{_AUX}\b|\s+(much|many|long|often|about|if|else|kind|type|sort|happens|"
    r"come|exactly|not)\b)"
)
_INVERTED = re.compile(rf"^{_AUX}(n't)?\s+{_SUBJECT}\b")
_TASK = re.compile(
    r"^(tell (me|us)|walk (me|us) through|talk (me|us) through|explain|describe|give (me|us)|write|implement|"
    r"design|show (me|us)|let'?s say|imagine|suppose|assume|what if|find|calculate|solve|compare|define|"
    r"list|sketch|estimate)\b"
)
_INDIRECT = re.compile(
    r"\b(i'?d (like|love) to (know|understand|hear)|i'?m curious|i wonder|i was wondering|"
    r"i don'?t know if you|any questions|(can|could) you (share|tell|explain|walk))\b"
)


def _normalize(text: str) -> str:
    t = text.strip().lower().replace("’", "'")
    while True:
        stripped = _FILLERS.sub("", t, count=1)
        if stripped == t:
            return t
        t = stripped


def looks_like_question(text: str) -> bool:
    """True when the line asks the listener something or gives them a task."""
    t = _normalize(text)
    if not t or _SMALL_TALK.search(t) or _REACTION.match(t):
        return False
    if "?" in t:
        return True
    return bool(_WH_QUESTION.match(t) or _INVERTED.match(t) or _TASK.match(t) or _INDIRECT.search(t))
