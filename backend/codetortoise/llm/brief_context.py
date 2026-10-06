"""The part of a review's brief a tier-2 prompt starts with (spec 2026-10-05-two-tier-stories §8), within 800 tokens:

- explain or Ask… on a finding: its story's title and purpose, the strong model's verdict and reason, its prepared facts;
- a story, flow or file: its story's purpose, what to check and open questions;
- @tortoise: the story of the anchor, if any, and the change overview.

Tier 2 builds on it: it never regroups the stories or overturns a verdict, and says so in its answer if it disagrees.
"""
from __future__ import annotations

from collections.abc import Iterable

from codetortoise import boardstore
from codetortoise.detectors.base import Finding
from codetortoise.facts_prep import finding_key
from codetortoise.store import Store
from codetortoise.stories import Story

BRIEF_CHARS = 3200                    # 800 tokens
HEAD = ("BRIEF (worked out by the strong model and by code; build on it: never regroup the stories or overturn a "
        "verdict, and if you disagree, say so in your answer):")


def _holding(stories: list[Story], story: str | None, finding: Finding | None, flow: str | None,
             nodes: Iterable[str]) -> Story | None:
    nodes = set(nodes)
    for st in stories:
        if (story is not None and st.id == story or finding is not None and finding.id in st.findings
                or flow is not None and flow in st.flows or nodes and nodes & set(st.nodes)):
            return st
    return None


def brief_context(store: Store, rid: int, *, story: str | None = None, finding: Finding | None = None,
                  flow: str | None = None, nodes: Iterable[str] = (), overview: bool = False) -> str:
    """The brief's lines for one target ("" when the brief knows nothing of it)."""
    ss = boardstore.stories(store, rid)
    brief = store.get_brief(rid) or {}
    st = _holding(ss.stories if ss else [], story, finding, flow, nodes)
    rows: list[str] = []
    if st is not None:
        rows.append(f"STORY: {st.title}" + (f" — {st.purpose}" if st.purpose else ""))
        if finding is None:
            rows += [f"What to check: {'; '.join(st.check)}"] if st.check else []
            rows += [f"Open questions: {'; '.join(st.questions)}"] if st.questions else []
    if finding is not None:
        if finding.verdict and finding.verdict_source == "tier1":
            rows.append(f"VERDICT (strong model): {finding.verdict} — {finding.verdict_reason}"
                        + (f" (cites {', '.join(finding.verdict_cites)})" if finding.verdict_cites else ""))
        facts = brief.get("facts", {}).get(finding_key(finding))
        rows += ["PREPARED FACTS:", facts] if facts else []
    if overview and brief.get("overview"):
        rows += ["CHANGE OVERVIEW:", brief["overview"]]
    if not rows:
        return ""
    text = "\n".join([HEAD] + rows)
    return text if len(text) <= BRIEF_CHARS else text[:BRIEF_CHARS - 1] + "…"
