"""Saving a board stage's result replaces an earlier run's boards, whole or not at all (boardstore)."""
import pytest

from codetortoise import boardstore
from codetortoise.board import About, Board, BoardSet, Overview
from codetortoise.store import Store


def _split(n: int, intent: str = "i") -> BoardSet:
    about = About(intent=intent)
    return BoardSet(overview=Overview(about=about), home={"N1": "C1"},
                    clusters={f"C{i}": Board(about=about) for i in range(1, n + 1)})


def test_a_rerun_with_fewer_clusters_leaves_no_stale_cluster_boards(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    boardstore.save(store, rid, _split(3), {})
    boardstore.save(store, rid, _split(2), {})
    assert set(boardstore.boards(store, rid)) == {"C1", "C2"}
    boardstore.save(store, rid, BoardSet(board=Board(about=About(intent="i"))), {})     # now fits on one board
    assert set(boardstore.boards(store, rid)) == {None}
    assert boardstore.overview(store, rid) is None and store.get_blob(rid, "node_cluster") is None
    assert store.blob_keys(rid, boardstore.PREFIX) == []


def test_saving_leaves_other_blobs_whose_keys_start_with_board_alone(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    store.put_blob(rid, "boardx", {"keep": 1})
    store.put_blob(rid, "overview_notes", {"keep": 2})
    boardstore.save(store, rid, _split(2), {})
    boardstore.save(store, rid, BoardSet(board=Board(about=About(intent="i"))), {})
    assert store.get_blob(rid, "boardx") == {"keep": 1} and store.get_blob(rid, "overview_notes") == {"keep": 2}


def test_a_save_that_fails_part_way_keeps_the_earlier_boards(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    boardstore.save(store, rid, _split(2, "old"), {})
    bad = _split(3, "new")
    bad.clusters["C3"] = object()                       # can't be stored: the save must fail before changing anything
    with pytest.raises(AttributeError):              # tag_board reads .nodes
        boardstore.save(store, rid, bad, {})
    bs = boardstore.boards(store, rid)
    assert set(bs) == {"C1", "C2"} and {b.about.intent for b in bs.values()} == {"old"}
    assert boardstore.overview(store, rid).about.intent == "old"
