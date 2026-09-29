from codetortoise.vcs.model import ClMeta, FileChange, stack


def fc(depot, action, before, after):
    return FileChange(depot=depot, local="/w/" + depot[2:], action=action, before=before, after=after)


def test_stack_chains_same_file_across_cls_in_cl_order():
    m1, m2 = ClMeta(cl=5, status="pending"), ClMeta(cl=3, status="submitted")
    files = stack([(m1, [fc("//d/a.c", "edit", "v2", "v3")]),
                   (m2, [fc("//d/a.c", "edit", "v1", "v2"), fc("//d/b.c", "add", "", "b")])])
    a, b = files
    assert (a.depot, a.before, a.after) == ("//d/a.c", "v1", "v3")
    assert [p.cl for p in a.per_cl] == [3, 5]
    assert (b.action, b.before, b.after) == ("add", "", "b")


def test_stack_delete_wins_and_readd_is_edit():
    m1, m2, m3 = (ClMeta(cl=i, status="pending") for i in (1, 2, 3))
    files = stack([(m1, [fc("//d/a.c", "edit", "v1", "v2")]), (m2, [fc("//d/a.c", "delete", "v2", "")])])
    assert files[0].action == "delete" and files[0].after == ""
    files = stack([(m2, [fc("//d/a.c", "delete", "v1", "")]), (m3, [fc("//d/a.c", "add", "", "new")])])
    assert files[0].action == "edit" and files[0].after == "new"
