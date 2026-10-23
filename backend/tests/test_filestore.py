"""Where a review's changed files live: the list without text, each file's change on its own (owner report
2026-10-23: opening a review sent every changed file's text)."""
from codetortoise import filestore
from codetortoise.store import Store
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange, PerClText


def _cs(*depots: str) -> ChangeSet:
    return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                     files=[FileChange(depot=d, local=d.replace("//d", "/w"), action="edit", before="a", after="b",
                                       base_rev="#3", per_cl=[PerClText(cl=1, before="a", after="b")]) for d in depots])


def test_the_list_names_each_changed_file_and_its_cls_and_the_file_holds_its_text(tmp_path):
    st = Store(tmp_path / "t.db")
    filestore.save(st, 1, _cs("//d/a.c", "//d/b.c"))
    assert filestore.listing(st, 1) == [
        {"depot": "//d/a.c", "local": "/w/a.c", "action": "edit", "base_rev": "#3", "cls": [1]},
        {"depot": "//d/b.c", "local": "/w/b.c", "action": "edit", "base_rev": "#3", "cls": [1]}]
    assert filestore.one(st, 1, "//d/a.c") == _cs("//d/a.c").files[0].model_dump()
    assert filestore.one(st, 1, "//d/c.c") is None
    assert st.get_blob(1, "changeset") == _cs("//d/a.c", "//d/b.c").model_dump()          # the whole change, as before


def test_a_rerun_with_fewer_files_leaves_no_stale_file(tmp_path):
    st = Store(tmp_path / "t.db")
    filestore.save(st, 1, _cs("//d/a.c", "//d/b.c"))
    filestore.save(st, 1, _cs("//d/a.c"))
    assert [f["depot"] for f in filestore.listing(st, 1)] == ["//d/a.c"]
    assert filestore.one(st, 1, "//d/b.c") is None


def test_a_review_stored_with_only_its_change_set_is_split_once_on_first_use(tmp_path):
    st = Store(tmp_path / "t.db")
    st.put_blob(1, "changeset", _cs("//d/a.c", "//d/b.c"))                   # as an older version stored the review
    assert filestore.one(st, 1, "//d/b.c")["after"] == "b"
    assert st.blob_keys(1, filestore.FILE) == [filestore.FILE + "//d/a.c", filestore.FILE + "//d/b.c"]
    assert [f["depot"] for f in filestore.listing(st, 1)] == ["//d/a.c", "//d/b.c"]
    assert filestore.listing(st, 2) == [] and filestore.one(st, 2, "//d/a.c") is None   # no change set: nothing to split


def test_a_split_keeps_a_list_stored_meanwhile(tmp_path):
    st = Store(tmp_path / "t.db")
    st.put_blob(1, "changeset", _cs("//d/old.c"))                            # read by a first use…
    filestore.save(st, 1, _cs("//d/new.c"))                                    # …while a re-run stores its files
    st.put_blob(1, "changeset", _cs("//d/old.c"))
    assert [f["depot"] for f in filestore.split(st, 1)] == ["//d/new.c"]
    assert filestore.one(st, 1, "//d/old.c") is None
