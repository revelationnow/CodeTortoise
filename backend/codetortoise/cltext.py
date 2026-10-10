"""CL descriptions as text (owner feedback 2026-10-10). Authors mix Markdown and HTML (`<span style=…>`) into their
descriptions; the CL page renders both, but a prompt or a one-line summary must not show the tags."""
from __future__ import annotations

import html
import re

_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_BLOCK = re.compile(r"^(#{1,6}\s+|>\s*|[-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+)")


def prompt_text(desc: str) -> str:
    """A description for a prompt: HTML tags gone and entities decoded, its Markdown and line breaks kept."""
    return html.unescape(_TAG.sub("", desc)).strip()


def first_line(desc: str) -> str:
    """A description's first non-blank line as plain text (the frontend's `plainTitle`): tags, block markers,
    emphasis, code ticks and link targets go; snake_case and spaced-out `a * b` stay."""
    s = next((ln.strip() for ln in prompt_text(desc).splitlines() if ln.strip()), "")
    prev = None
    while prev != s:
        prev, s = s, _BLOCK.sub("", s)
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"(\*\*|__)(\S(?:.*?\S)?)\1", r"\2", s)
    s = re.sub(r"~~(\S(?:.*?\S)?)~~", r"\1", s)
    s = re.sub(r"\*(\S(?:.*?\S)?)\*", r"\1", s)
    s = re.sub(r"(^|\W)_(\S(?:.*?\S)?)_(?=\W|$)", r"\1\2", s)
    return s.strip()
