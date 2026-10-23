"""Where a review's changed files live (owner report 2026-10-23: opening a review sent every changed file's text).

The blob `changeset` holds the whole change, for the pipeline and the AI. Beside it, `changed_files` lists the changed
files without their text and `changed_file:<depot>` holds one file's change, so the browser reads the list, and a file's
text when it shows that file. A review stored before these gets them from its change set on first use.
"""
from __future__ import annotations

import threading

from codetortoise.store import Store
from codetortoise.vcs.model import ChangeSet

LISTING = "changed_files"
FILE = "changed_file:"
_lock = threading.Lock()                # a first use's split never writes over the files a re-run stored meanwhile


def _entry(f: dict) -> dict:
    """A changed file as the list shows it: no text, and the CLs that touch it."""
    return {"depot": f["depot"], "local": f["local"], "action": f["action"], "base_rev": f.get("base_rev"),
            "cls": [p["cl"] for p in f.get("per_cl", [])]}


def save(store: Store, rid: int, cs: ChangeSet) -> None:
    """Store an ingest's change set, its list and each file's change, replacing an earlier run's in one write."""
    puts = {"changeset": cs, LISTING: [_entry(f.model_dump()) for f in cs.files]} | {FILE + f.depot: f for f in cs.files}
    with _lock:
        store.replace_blobs(rid, ["changeset", LISTING], [FILE], puts)


def split(store: Store, rid: int) -> list[dict] | None:
    """The list of a review stored before it, made with each file's change from the review's change set (None: no
    change set); a list stored meanwhile is kept."""
    with _lock:
        got = store.get_blob(rid, LISTING)
        if got is not None:
            return got
        cs = store.get_blob(rid, "changeset")
        if cs is None:
            return None
        files = cs.get("files", [])
        listing = [_entry(f) for f in files]
        store.replace_blobs(rid, [LISTING], [FILE], {LISTING: listing} | {FILE + f["depot"]: f for f in files})
        return listing


def listing(store: Store, rid: int) -> list[dict]:
    """The review's changed files without their text, in the change set's order."""
    got = store.get_blob(rid, LISTING)
    return (got if got is not None else split(store, rid)) or []


def one(store: Store, rid: int, depot: str) -> dict | None:
    """One changed file's change as the change set holds it: its text before and after, and each CL's; None for a file
    the change does not touch."""
    got = store.get_blob(rid, FILE + depot)
    if got is None and not store.has_blob(rid, LISTING) and split(store, rid) is not None:
        got = store.get_blob(rid, FILE + depot)
    return got
