"""The design context (spec 2026-11-02 §8): what the code can't say, given by the review's owner — free notes,
documents (pasted, from a file, or a link the server can read), conditions added or left out by hand and a choice of
components. The overview's opening and its design parts read it; stories, flows and checks never do, so it can't change
what is flagged."""
from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from codetortoise.config import ComponentRule

CAP = 12_000                 # characters of it the prompts read, documents included once read (§8, §14)
BLOB = "design_context"      # where a review keeps it


class ContextDoc(BaseModel):
    """A document of the context: its text, pasted, from a file, or read from `url` once when the context was saved."""
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=CAP)
    url: str | None = Field(default=None, max_length=2000)


class HandCondition(BaseModel):
    """A condition the owner adds: its test as the code writes it ("len > 64"), and the function holding it when the
    test alone does not find it."""
    test: str = Field(min_length=1, max_length=300)
    function: str | None = Field(default=None, max_length=200)


class HandConditions(BaseModel):
    add: list[HandCondition] = Field(default_factory=list, max_length=10)
    remove: list[str] = Field(default_factory=list, max_length=20)        # tests of conditions the rules found


class DesignContext(BaseModel):
    notes: str = Field(default="", max_length=CAP)
    documents: list[ContextDoc] = Field(default_factory=list, max_length=10)
    conditions: HandConditions = Field(default_factory=HandConditions)
    components: list[ComponentRule] = Field(default_factory=list, max_length=30)   # empty: analysis.components


def context_text(c: DesignContext) -> str:
    """What the prompts read of it: the notes, then each document under its name."""
    parts = [c.notes.strip()] if c.notes.strip() else []
    parts += [f"DOCUMENT {d.name.strip()}:\n{d.text.strip()}" for d in c.documents if d.text.strip()]
    return "\n\n".join(parts)


def context_hash(c: DesignContext) -> str | None:
    """Which text the opening was written from (§9's `context_hash`); None when the context has none to read."""
    text = context_text(c)
    return hashlib.sha256(text.encode()).hexdigest()[:12] if text else None


def over_cap(c: DesignContext) -> str | None:
    """Why the context is too long to keep (§8: at most CAP characters once its documents are read), or None."""
    n = len(context_text(c))
    if n <= CAP:
        return None
    return f"The design context is {n:,} characters; it holds at most {CAP:,}. Shorten the notes or a document."


def same_test(a: str, b: str) -> bool:
    """Two tests are the same when they differ only in spacing: `len>64` is `len > 64`."""
    return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)


def load_context(store, rid: int) -> DesignContext:
    """A review's design context; an empty one when it has none."""
    raw = store.get_blob(rid, BLOB)
    return DesignContext.model_validate(raw) if raw else DesignContext()
