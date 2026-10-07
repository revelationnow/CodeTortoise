"""The AI call ledger (spec 2026-10-03 §2): every call is reserved against the limits, recorded, and finished.

Limits are in calls. A reservation checks the review's budget and the person's daily limit and records the call in
one step under the store's lock, so concurrent requests can't overrun a budget. Failed calls count; refused ones are
recorded but cost nothing. The pipeline (user None) doesn't count against anyone's daily limit.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from codetortoise.config import LlmBudget
from codetortoise.llm.client import LlmClient
from codetortoise.store import Store

T = TypeVar("T")
PIPELINE = "pipeline"
TIER1 = ("stories", "stories_merge", "review", "threads")    # strong-model calls: their own budget (spec 2026-10-05 §9)
_T1 = "(" + ",".join(f"'{p}'" for p in TIER1) + ")"


class Refused(Exception):
    """A call over a limit: not made. `reason` is shown to the person who asked."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, store: Store, budget: LlmBudget):
        self.store, self.limits = store, budget

    # ---- limits
    def budget(self, rid: int) -> int:
        rows = self.store._all("SELECT budget FROM llm_budget WHERE review_id=? ORDER BY rowid DESC LIMIT 1", (rid,))
        return rows[0]["budget"] if rows else self.limits.per_review

    def raise_budget(self, rid: int, total: int, by: str) -> None:
        self.store._exec("INSERT INTO llm_budget VALUES(?,?,?,?)", (rid, int(total), by, _now()))

    def rounds(self, rid: int) -> int:
        """Rounds one @tortoise answer on review `rid` may take (the whole answer is one call)."""
        rows = self.store._all("SELECT rounds FROM llm_rounds WHERE review_id=? ORDER BY rowid DESC LIMIT 1", (rid,))
        return rows[0]["rounds"] if rows else self.limits.per_mention

    def set_rounds(self, rid: int, rounds: int, by: str) -> None:
        self.store._exec("INSERT INTO llm_rounds VALUES(?,?,?,?)", (rid, int(rounds), by, _now()))

    def used(self, rid: int) -> int:
        """Tier-2 calls on the review: everyone's and the pipeline's, not the strong model's."""
        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE review_id=? AND outcome != 'refused' "
                               f"AND purpose NOT IN {_T1}", (rid,))[0]["n"]

    def tier1_used(self, rid: int) -> int:
        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE review_id=? AND outcome != 'refused' "
                               f"AND purpose IN {_T1}", (rid,))[0]["n"]

    def person_today(self, user: str) -> int:
        day = datetime.now(UTC).date().isoformat()
        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE user=? AND outcome != 'refused' "
                               "AND started_at >= ?", (user, day))[0]["n"]

    def check(self, rid: int | None, user: str | None, purpose: str | None = None) -> str | None:
        """Why a call by `user` on review `rid` would be refused now, or None."""
        if rid is not None and purpose in TIER1:
            n = self.limits.tier1_per_review
            return f"this review has used its {n} tier-1 AI calls" if self.tier1_used(rid) >= n else None
        if rid is not None:
            budget = self.budget(rid)
            if self.used(rid) >= budget:
                return f"this review has used its {budget} AI calls; the owner can raise it"
        if user and self.person_today(user) >= self.limits.per_person_daily:
            return f"you've used your {self.limits.per_person_daily} AI calls today"
        return None

    # ---- calls
    def reserve(self, rid: int | None, user: str | None, purpose: str, target: str) -> int:
        """Record a call about to be made and return its id, or raise Refused (recording the refusal)."""
        with self.store._lock:
            reason = self.check(rid, user, purpose)
            cur = self.store._exec(
                "INSERT INTO llm_calls(review_id, user, purpose, target, started_at, outcome, error) VALUES(?,?,?,?,?,?,?)",
                (rid, user or PIPELINE, purpose, target, _now(), "refused" if reason else "running", reason))
            if reason:
                raise Refused(reason)
            return int(cur.lastrowid)

    def finish(self, call_id: int, outcome: str, usage: tuple[int, int] | None = None, error: str | None = None) -> None:
        p, c = usage if usage else (None, None)
        self.store._exec("UPDATE llm_calls SET finished_at=?, outcome=?, prompt_tokens=?, completion_tokens=?, error=? "
                         "WHERE id=?", (_now(), outcome, p, c, error, call_id))

    def call(self, llm: LlmClient, rid: int | None, user: str | None, purpose: str, target: str,
             fn: Callable[[LlmClient], T]) -> T:
        """Reserve, run `fn(llm)` (one AI call, its retries included), and record the outcome and tokens."""
        call_id = self.reserve(rid, user, purpose, target)
        llm.start_usage()
        try:
            out = fn(llm)
        except Exception as e:
            self.finish(call_id, "failed", llm.take_usage(), f"{type(e).__name__}: {e}"[:500])
            raise
        self.finish(call_id, "ok", llm.take_usage())
        return out

    def fail_running(self) -> None:
        """At startup: calls a stopped server left running count as failed (they may have cost tokens)."""
        self.store._exec("UPDATE llm_calls SET finished_at=?, outcome='failed', error='interrupted by a restart' "
                         "WHERE outcome='running'", (_now(),))

    # ---- reporting
    def workspace_calls(self) -> int:
        """Calls made for the workspace rather than a review (layer naming)."""
        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE review_id IS NULL AND outcome != 'refused'"
                               )[0]["n"]

    def usage(self, rid: int) -> dict:
        calls = self.store._all("SELECT id, user, purpose, target, started_at, finished_at, prompt_tokens, "
                                "completion_tokens, outcome, error FROM llm_calls WHERE review_id=? ORDER BY id", (rid,))
        counted = [c for c in calls if c["outcome"] != "refused"]
        tier1 = [c for c in counted if c["purpose"] in TIER1]
        return {"used": len(counted) - len(tier1), "budget": self.budget(rid),
                "tier1": {"used": len(tier1), "budget": self.limits.tier1_per_review},
                "by_person": dict(Counter(c["user"] for c in counted)),
                "by_purpose": dict(Counter(c["purpose"] for c in counted)), "calls": calls}
