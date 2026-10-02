"""House style for LLM-written analysis: the Microsoft Writing Style Guide, and one Diátaxis mode per output.

The rules go into the prompts; `check_style` verifies the ones a program can check reliably, so text that breaks them
is dropped in favour of the deterministic text. Voice and tense stay prompt-only (no reliable check).
"""
from __future__ import annotations

import re

STYLE = ("Write for the reviewer following the Microsoft Writing Style Guide: address the reader as \"you\", use active "
         "voice and present tense, keep sentences to 25 words or fewer, use plain words and natural contractions, write "
         "numbers as numerals, and write code names exactly as they appear. Never use \"please\", \"simply\", \"just\", "
         "\"easy\", \"e.g.\", \"i.e.\", \"etc.\" or exclamation marks.")

MODES = {
    "explanation": ("Diátaxis mode: explanation. Say why this happens and what follows from it, with the context a "
                    "reviewer needs. Don't give instructions or steps."),
    "how-to": ("Diátaxis mode: how-to guide. Each verification step is one action that starts with an imperative verb "
               "(for example \"Check\", \"Run\", \"Confirm\"), in the order a reviewer does them."),
    "headline": "Headline: 8 words or fewer, sentence case, no final period.",
}

_CODE = re.compile(r"`[^`]*`")
_BANNED = re.compile(r"\b(please|simply|just|easy|easily)\b|\be\.g\.|\bi\.e\.|\betc\.|(?<=\w)!(?=\s|$)", re.I)
_SENTENCE = re.compile(r"(?<=[.?!])\s+")
_NOT_VERBS = {"the", "a", "an", "this", "that", "these", "those", "it", "its", "you", "we", "i", "there", "if", "when",
              "each", "every", "all", "some", "no"}


def check_style(text: str, mode: str) -> list[str]:
    """The checkable style problems in `text` written in `mode` ("explanation", "how-to" or "headline")."""
    prose = _CODE.sub("code", text)
    problems = [f"avoid {m.group(0)!r}" for m in _BANNED.finditer(prose)]
    if any(len(s.split()) > 30 for s in _SENTENCE.split(prose.strip())):
        problems.append("sentence over 30 words")
    if mode == "headline":
        if prose.rstrip().endswith("."):
            problems.append("headline ends with a period")
        if len(prose.split()) > 8:
            problems.append("headline over 8 words")
    if mode == "how-to":
        first = prose.split()[0].strip(",:").lower() if prose.split() else ""
        if (not first.isalpha() or first in _NOT_VERBS or first.endswith(("ing", "ed"))
                or (first.endswith("s") and not first.endswith("ss") and first != "focus")):
            problems.append("step does not start with an imperative verb")
    return problems
