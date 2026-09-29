from codetortoise.diffmap import map_changes
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def test_cl101_body_change_with_written_members(fx_source):
    dm = map_changes(fx_source.load([101]))
    assert [(f.qualname, f.kind, f.written_members) for f in dm.functions] == [("uart_send", "body_modified", ["tx"])]
    assert dm.types == []


def test_cl102_signature_type_and_decl_changes(fx_source):
    dm = map_changes(fx_source.load([102]))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("hal_write", "signature_changed")]
    assert sorted((t.name, t.kind) for t in dm.types) == [("Uart", "type_changed"), ("hal_write", "decl_changed")]


def test_added_removed_and_non_source_files():
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/x.c", local="/w/x.c", action="edit",
                   before="int a(void){return 1;}\nint b(void){return 2;}\n",
                   after="int b(void){return 2;}\nint c(void){return 3;}\n"),
        FileChange(depot="//d/README.txt", local="/w/README.txt", action="edit", before="a", after="b")])
    dm = map_changes(cs)
    assert sorted((f.qualname, f.kind) for f in dm.functions) == [("a", "removed"), ("c", "added")]
    assert dm.changed_files == ["/w/x.c"]
