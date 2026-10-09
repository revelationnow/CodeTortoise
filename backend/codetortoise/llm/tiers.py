"""Tries for one piece of strong-model work (spec 2026-10-08-llm-robustness §5): the strong model, the strong model in
a fresh conversation at double its limit, then the weak model at four times, each its own ledger call. The stage
decides its own last resort when every try fails."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from codetortoise.llm.client import LlmClient, LlmTruncated, LlmUnreachable
from codetortoise.llm.ledger import Ledger, Refused

Tier = Literal["strong", "fresh", "weak"]


@dataclass
class Tried[T]:
    value: T
    tier: Tier
    model: str
    failures: list[str] = field(default_factory=list)   # the tries before it, worded for a note
    strong_unreachable: bool = False


class TiersFailed(Exception):
    def __init__(self, failures: list[str], strong_unreachable: bool):
        super().__init__("; ".join(failures) or "no model to try")
        self.failures, self.strong_unreachable = failures, strong_unreachable


def failure_text(e: Exception) -> str:
    if isinstance(e, LlmUnreachable):
        return "unreachable"
    if isinstance(e, LlmTruncated):
        return str(e)
    s = str(e)
    if s.startswith("LLM returned invalid JSON twice"):
        return "invalid JSON twice"
    if s.startswith("LLM HTTP "):
        return s[4:124]
    return f"{type(e).__name__}: {s}"[:120]


def tried_note(prefix: str, failures: list[str], outcome: str) -> str:
    return f"{prefix}: " + "; ".join([*failures, outcome])


def done_text(t: Tried, verb: str) -> str:
    """Who did the work: "small grouped its pieces", or "big … on a fresh try"."""
    return f"{t.model} {verb}" + (" on a fresh try" if t.tier == "fresh" else "")


def try_tiers[T](ledger: Ledger | None, rid: int | None, purpose: str, target: str, fn: Callable[[LlmClient], T],
              strong: LlmClient, weak: LlmClient | None, skip_strong: bool = False) -> Tried[T]:
    """`fn` on each try in turn until one answers. Refused (the budget) stops at once; an unreachable strong model
    is not tried fresh; `skip_strong` starts at the weak model. Raises TiersFailed when every try failed."""
    tries: list[tuple[Tier, LlmClient, str, str]] = []
    if not skip_strong:
        tries += [("strong", strong.with_start(strong.max_output_tokens), target, strong.model),
                  ("fresh", strong.with_start(min(strong.cap, 2 * strong.base)), f"{target} (fresh)", "fresh try")]
    if weak is not None:
        tries.append(("weak", weak.with_start(min(weak.cap, 4 * max(weak.base, strong.base))), f"{target} (weak)",
                      weak.model))
    failures: list[str] = []
    unreachable = False
    for tier, llm, tgt, label in tries:
        if tier == "fresh" and unreachable:
            continue
        try:
            value = ledger.call(llm, rid, None, purpose, tgt, fn) if ledger is not None else fn(llm)
        except Refused:
            raise
        except Exception as e:  # this try failed: the next one goes on
            failures.append(f"{label}: {failure_text(e)}")
            unreachable = unreachable or (tier == "strong" and isinstance(e, LlmUnreachable))
            continue
        return Tried(value, tier, llm.model, failures, unreachable)
    raise TiersFailed(failures, unreachable)
