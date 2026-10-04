# Large-Change Boards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A change too big for one board gets an overview of its clusters (connected changed code) and one board per cluster of at most 30 nodes, with visitors, "+N callers" expansion and links between clusters; small changes keep today's single board; a lab script imports libgit2's large merges into Perforce to test it at size.

**Architecture:** The board stage computes impacts and flows once, then `clusters.cluster_change` groups the changed code (joined by calls and by field accesses the change altered, split and merged to fit 30 nodes) and `board.build_boards` renders one board per cluster with the existing board code, plus an `Overview`. `boardstore` keeps the blobs (`board` or `overview` + `board:C<n>` + `node_cluster`); new endpoints serve the overview, cluster boards with expansion, and `locate`. The frontend adds an overview page and a cluster route around today's `Board`.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, pytest, ruff; React 19, TypeScript (strict), Vite, vitest, Playwright; Helix Core `p4`/`p4d` r26.1 for the lab. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-03-large-change-boards-design.md`

**Base:** `main` (the spec is its latest commit).

**Provenance:** every code block was run before the plan was written, and the boards were checked on nine real libgit2 changelists (lab README). The tasks were then replayed in order on a fresh tree from `main`: each task's tests failed before its implementation and passed after it, and the suite stayed green after every task. The replayed tree is byte-identical to the validated one. New files are given in full; changes to existing files are unified diffs against the previous task's state (`git apply`, or by hand).

## Global Constraints

- **Budget:** a board shows at most `analysis.board_max_nodes: 30` nodes before expansion; changed code and flow nodes are never cut (only a cluster merged past the 60-cluster limit may exceed 30). Defaults `cluster_min_changed: 3`, `overview_max_clusters: 60`, `expand_step: 10`; `max_flows` and `board_blast_nodes` are accepted and ignored.
- **Fields:** only field accesses the change added or removed join code and are required; fields used as before only fill spare room.
- **Small changes:** a change whose required nodes fit in 30 keeps today's single `board` blob, keys and page; old reviews show their board.
- **Messages:** "That cluster no longer exists after the re-run." (404), "this review is shown as one board" (overview 404), "this review is split into clusters: see its overview" (board 404), "shown as one board (clustering failed: …)" (degraded stage).
- **Lab:** `lab/p4-import.py` runs by hand, never as a service; it never writes into a depot path that already has files; kill any `p4d` it starts by the PID it prints.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

Conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **One function touching dozens of fields** (pcre2's compiler in libgit2 touches about 70) must still give boards of at most 30 nodes, keeping the function and its flows. Pinned by `test_one_function_touching_too_many_fields_is_one_cluster_not_a_part` (Task 1) and `test_a_board_leaves_out_fields_past_the_budget_but_never_changed_code_or_flows` (Task 2).
2. **A mechanical change across untouched code** (a rename at 139 call sites whose functions each read 15 fields) must not shatter into dozens of boards. Pinned by `test_only_field_accesses_the_change_added_or_removed_join_code_and_are_required`, `test_files_share_a_board_while_they_fit`, `test_small_clusters_merge_into_the_nearest_directory_but_not_across_top_directories` (Task 1) and `test_fields_whose_access_did_not_change_fill_spare_room_but_never_split_the_review` (Task 2).
3. **No flow lost or shown twice** across cluster boards, and every changed function at home on exactly one board. Pinned by `test_every_changed_function_and_flow_is_on_exactly_one_board` (Task 2).
4. **A bookmarked cluster board after a re-run** renumbered the clusters: a clear 404 message, not a crash. Pinned by `test_the_api_serves_the_overview_and_each_cluster_board` (Task 3).
5. **Reset hidden under an open code card** on a cluster board past 30 nodes. Pinned by the e2e test "+N callers adds them past the budget, and Reset takes them away" (Task 4).

## Spec Coverage

| Spec | Where |
|---|---|
| §2 clusters (join, tests apart, split, merge, names, order, many clusters, flows, findings, placement, links) | Tasks 1, 2 |
| §3 boards (required, visitors, neighbours, badges, expansion, hidden) | Tasks 2, 3, 4 |
| §4 data and API (blobs, endpoints, ✦ Explain, up-front pass, file tags, configuration) | Tasks 2, 3 |
| §5 interface (routes, overview, cluster board, findings, phone) | Task 4 |
| §6 limits and failures (fallback board, old reviews) | Task 2 |
| §7 lab | Task 5 |
| §8 testing | every task |

## Decisions the spec left open

- **Expansions live in the page address** (`?x=N12:callers`) and are remembered per cluster in browser storage; Reset clears both.
- **A cluster board's change panel** lists only the cluster's files and findings; the overview's panel covers the whole change.
- **The board's toolbar sits above open code cards** (z-index 51 over 50): on a cluster board past 30 nodes an open card could otherwise cover Reset.
- **A new `p4d` needs a password** (r26 refuses commands without one): the lab script sets the first user's password (default as `lab/setup.sh`, `OWNER_PASSWD` or `--password`) and logs in.
- **`cls.tsv` counts C/C++ files outside tests**, like `--list`, so its numbers match the selection rule.
- **The libgit2 base is `1de5a32dd^1`**: a base at the 2024-10-01 date boundary would already include #6896.

---

### Task 1: Clusters of a large change's changed code

Spec §2. `cluster_change` groups a change's changed functions and fields into clusters whose boards fit in
`max_nodes` (30) nodes. Two changed functions **join** when one calls the other, or both have an access the change
added or removed (`Edge.status` `added`/`removed`) to the same field; unchanged code they share (a logger) and fields
they use as before never join them; test code (`is_test`) stays apart. A cluster's **required** nodes are its changed
code, the fields whose access it changed and every node on its flows. A cluster over the budget **splits** by module,
then directory, then file; parts under one directory share a board while they fit, but two top directories of the
change never do; a single file is cut into runs of functions in source order; a single function is split by its flows
("… (1 of 2)"), sized without its fields. Clusters of fewer than `min_changed` (3) changed functions **merge** into
the nearest directory's cluster below the change's root, within the budget; over `max_clusters` (60) the smallest
merge further, past the budget, and `merged_over_limit` says how many. **Names** are the deepest shared directory
relative to the change's root (several top directories: `deps/reftable + src/libgit2`), with the main function
appended to tell same-named clusters apart; **order** is riskiest first (finding severity, flows, changed functions,
name) with ids `C1…`; **placement** is the layer of most of its changed functions, other layers in `also`. `home`
maps every changed node, and every unchanged required node with a home directory, to its cluster.

**Files:**
- Create: `backend/codetortoise/clusters.py`
- Test: `backend/tests/test_clusters.py`

**Interfaces:**
- Consumes: `impact.ImpactModel`, `Edge.status`, `detectors.base.Finding`, `SEVERITY_RANK`; `board.is_test_path` (tests).
- Produces: `clusters.Cluster(members, flows, required, part, of, test, id, name, findings, risk, level, also)`;
  `Clustering(clusters, home, merged_over_limit)`; `cluster_change(im, flows, findings, *, is_test, module_of=None,
  max_nodes=30, min_changed=3, max_clusters=60) -> Clustering` (a flow needs `id`, `path`, `cause`);
  `altered_access(edge) -> bool`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_clusters.py`:

```python
"""Clusters of a large change (spec 2026-10-03-large-change-boards §2), on synthetic impact graphs."""
from types import SimpleNamespace

from codetortoise.board import is_test_path
from codetortoise.clusters import cluster_change
from codetortoise.detectors.base import Finding
from codetortoise.impact import Edge, ImpactModel, Node


class G:
    """A tiny impact graph: functions by file, changed or not, with call and field edges."""

    def __init__(self):
        self.im = ImpactModel()
        self.flows = []

    def fn(self, label, file, changed=True, layer=None, line=None):
        nid = f"N{len(self.im.nodes) + 1}"
        self.im.nodes[nid] = Node(id=nid, key=f"c:{label}", label=label, file=f"/ws/{file}", layer=layer,
                                  line=line or len(self.im.nodes) + 1, status="changed" if changed else "unchanged")
        if changed:
            self.im.changed.append(nid)
        return nid

    def field(self, label):
        nid = f"N{len(self.im.nodes) + 1}"
        self.im.nodes[nid] = Node(id=nid, key=f"field:{label}", label=label, kind="field")
        return nid

    def edge(self, src, dst, kind="call", status="unchanged"):
        self.im.edges.append(Edge(id=f"E{len(self.im.edges) + 1}", src=src, dst=dst, kind=kind, status=status))

    def flow(self, cause, *path):
        f = SimpleNamespace(id=f"FL{len(self.flows) + 1}", path=[*path, cause] if cause not in path else list(path),
                            cause=cause)
        self.flows.append(f)
        return f

    def run(self, findings=(), **kw):
        kw.setdefault("min_changed", 1)
        return cluster_change(self.im, self.flows, list(findings), is_test=self.is_test, **kw)

    def is_test(self, nid):
        return is_test_path(self.im.nodes[nid].file[len("/ws/"):]) if self.im.nodes[nid].file else False


def members(res):
    return sorted(sorted(c.members) for c in res.clusters)


def test_changed_code_joins_by_calls_and_shared_fields_but_not_by_a_common_helper():
    g = G()
    log = g.fn("log", "util/log.c", changed=False)
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("uart_write", "drv/uart.c")
    c, d = g.fn("logger_flush", "svc/logger.c"), g.fn("logger_put", "svc/logger.c")
    buf = g.field("Logger::buf")
    g.edge(a, b)
    g.edge(c, buf, "writes", "added")
    g.edge(d, buf, "reads", "removed")
    for n in (a, b, c, d):
        g.edge(n, log)                                       # everyone calls the logger: no join
    assert members(g.run()) == sorted([sorted([a, b]), sorted([c, d])])


def test_only_field_accesses_the_change_added_or_removed_join_code_and_are_required():
    g = G()
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("logger_put", "svc/logger.c")
    cfg, buf = g.field("Uart::cfg"), g.field("Logger::buf")
    g.edge(a, cfg, "reads")
    g.edge(b, cfg, "reads")                                  # both read it, as they did before the change
    g.edge(a, buf, "writes", "added")
    res = g.run()
    assert members(res) == sorted([[a], [b]])
    send = next(c for c in res.clusters if a in c.members)
    assert buf in send.required and cfg not in send.required


def test_changed_test_code_is_its_own_cluster():
    g = G()
    a = g.fn("uart_send", "drv/uart.c")
    t = g.fn("test_uart_send", "tests/test_uart.c")
    g.edge(t, a)
    res = g.run()
    assert members(res) == sorted([[a], [t]])
    assert next(c for c in res.clusters if t in c.members).test is True


def test_a_cluster_over_the_budget_splits_by_directory_then_packs_a_file():
    g = G()
    chain = [g.fn(f"d{i}", "drv/a.c") for i in range(20)] + [g.fn(f"s{i}", "svc/b.c") for i in range(20)]
    for x, y in zip(chain, chain[1:], strict=False):
        g.edge(x, y)                                          # one connected group of 40
    res = g.run()
    assert [len(c.members) for c in sorted(res.clusters, key=lambda c: c.name)] == [20, 20]
    one = G()
    fns = [one.fn(f"f{i}", "drv/a.c", line=i + 1) for i in range(40)]
    for x, y in zip(fns, fns[1:], strict=False):
        one.edge(x, y)
    packed = one.run()
    assert sorted(len(c.members) for c in packed.clusters) == [10, 30]
    assert all(len(c.required) <= 30 for c in packed.clusters)


def test_files_share_a_board_while_they_fit():
    g = G()
    fns = [g.fn(f"{f}{i}", f"drv/{f}.c") for f in "abc" for i in range(12)]
    for x, y in zip(fns, fns[1:], strict=False):
        g.edge(x, y)                                          # one group of 36 in three files of 12
    assert sorted(len(c.members) for c in g.run().clusters) == [12, 24]


def test_one_function_with_too_many_flows_is_split_into_flow_groups():
    g = G()
    f = g.fn("uart_send", "drv/uart.c")
    for i in range(20):
        g.flow(f, g.fn(f"caller{i}", "app/x.c", changed=False), g.fn(f"top{i}", "app/y.c", changed=False))
    res = g.run()
    parts = sorted(res.clusters, key=lambda c: c.part)
    assert [c.part for c in parts] == [(1, 2), (2, 2)]
    assert [len(c.required) <= 30 for c in parts] == [True, True]
    assert sorted(fid for c in parts for fid in c.flows) == sorted(fl.id for fl in g.flows)   # each flow once
    assert parts[0].members == [f] and parts[1].members == [] and res.home[f] == parts[0].id
    assert parts[0].name.endswith("uart_send (1 of 2)") and parts[1].name.endswith("uart_send (2 of 2)")


def test_small_clusters_merge_into_the_nearest_directory_but_not_across_top_directories():
    g = G()
    it = [g.fn(f"t{i}", "tests/iter/t.c") for i in range(4)]
    src = [g.fn(f"s{i}", "src/a.c") for i in range(4)]
    for chain in (it, src):
        for x, y in zip(chain, chain[1:], strict=False):
            g.edge(x, y)
    p, q = g.fn("pack_t", "tests/pack/p.c"), g.fn("graph_t", "tests/graph/g.c")
    z = g.fn("fuzz", "fuzzers/f.c")
    assert members(g.run(min_changed=3)) == sorted([sorted([*it, p, q]), sorted(src), [z]])


def test_small_clusters_merge_within_a_directory_first():
    g = G()
    a, b, c = g.fn("a", "drv/x.c"), g.fn("b", "drv/x.c"), g.fn("c", "drv/y.c")
    z = g.fn("z", "svc/z.c")
    g.edge(b, c)
    res = g.run(min_changed=3)
    assert members(res) == sorted([sorted([a, b, c]), [z]])


def test_too_many_clusters_merge_and_say_how_many():
    g = G()
    for i in range(5):
        g.fn(f"f{i}", f"d{i}/x.c")
    res = g.run(max_clusters=3)
    assert len(res.clusters) == 3 and res.merged_over_limit == 2
    assert sorted(m for c in res.clusters for m in c.members) == sorted(g.im.changed)


def test_names_order_ids_and_placement():
    g = G()
    a, b = g.fn("uart_send", "drv/uart/uart.c", layer=1), g.fn("uart_init", "drv/uart/uart.c", layer=1)
    c = g.fn("logger_flush", "svc/logger/log.c", layer=2)
    d = g.fn("regs_write", "drv/uart/regs.c", layer=0)
    g.edge(a, b)
    g.edge(a, d)
    f1 = Finding(id="F1", kind="contract", severity="high", title="t", nodes=[c], evidence=[], summary="s")
    f2 = Finding(id="F2", kind="contract", severity="medium", title="t", nodes=[a], evidence=[], summary="s")
    res = g.run(findings=[f2, f1])
    assert [(c_.id, c_.name, c_.risk) for c_ in res.clusters] == [("C1", "svc/logger", "high"), ("C2", "drv/uart", "medium")]
    uart = res.clusters[1]
    assert uart.level == 1 and uart.also == [0] and uart.findings == ["F2"]
    assert res.home[a] == "C2" and res.home[c] == "C1"


def test_two_clusters_in_one_directory_are_told_apart_by_their_main_function():
    g = G()
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("uart_tx", "drv/uart.c")
    c, d = g.fn("uart_init", "drv/uart.c"), g.fn("uart_cfg", "drv/uart.c")
    g.edge(a, b)
    g.edge(c, d)
    names = sorted(c_.name for c_ in g.run(min_changed=1).clusters)
    assert names[0].startswith("drv · ") and names[1].startswith("drv · ") and names[0] != names[1]


def test_a_cluster_spanning_top_directories_is_named_by_them():
    g = G()
    a, b = g.fn("rt_write", "deps/reftable/basics.c"), g.fn("refdb_write", "src/libgit2/refdb.c")
    g.edge(b, a)
    assert [c.name for c in g.run().clusters] == ["deps/reftable + src/libgit2"]


def test_unchanged_nodes_on_a_flow_live_with_their_directory():
    g = G()
    a = g.fn("uart_send", "drv/uart.c")
    s = g.fn("logger_put", "svc/logger.c")
    land = g.fn("logger_flush", "svc/logger.c", changed=False)
    g.flow(a, land)
    res = g.run()
    by_member = {m: c.id for c in res.clusters for m in c.members}
    assert res.home[land] == by_member[s]                    # a visitor on drv's board, at home with svc's code
    assert land in next(c for c in res.clusters if a in c.members).required


def test_parts_in_different_directories_never_share_a_board():
    g = G()
    fns = [g.fn(f"a{i}", "app/x.c") for i in range(12)] + [g.fn(f"d{i}", "drv/y.c") for i in range(12)]
    fns += [g.fn(f"s{i}", "svc/z.c") for i in range(12)]
    for x, y in zip(fns, fns[1:], strict=False):
        g.edge(x, y)                                          # 36 in three top directories: three boards
    assert sorted(c.name for c in g.run().clusters) == ["app", "drv", "svc"]


def test_one_function_touching_too_many_fields_is_one_cluster_not_a_part():
    g = G()
    f = g.fn("pcre_compile2", "deps/pcre.c")
    for i in range(40):
        g.edge(f, g.field(f"compile_data::f{i}"), "writes", "added")
    g.flow(f, g.fn("caller", "src/regexp.c", changed=False))
    (c,) = g.run().clusters
    assert c.part is None and c.members == [f] and c.name == "deps" and len(c.flows) == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_clusters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.clusters'` (collection stops: `1 error`)

- [ ] **Step 3: Implement**

`backend/codetortoise/clusters.py`:

```python
"""Clusters of a large change (spec 2026-10-03-large-change-boards §2).

Changed functions and fields are joined when changed code calls changed code or shares a field whose access the
change added or removed; unchanged code they have in common (a logger everyone calls) never joins them. A cluster whose
board would need more than `max_nodes` nodes is split by module, directory, file, then by its flows, with whole parts
sharing a board while they fit; clusters of fewer than `min_changed` changed functions are merged into the nearest
directory's. Every changed node and every flow ends up in exactly one cluster.
"""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.impact import ImpactModel


@dataclass
class Cluster:
    members: list[str]                                # changed nodes whose home is this cluster
    flows: list[str] = field(default_factory=list)    # flow ids, each in exactly one cluster
    required: list[str] = field(default_factory=list)  # nodes its board must show (members, fields, flow nodes)
    part: tuple[int, int] | None = None               # (i, n) when one function's flows were split over n boards
    of: str | None = None                             # that function
    test: bool = False
    id: str = ""
    name: str = ""
    findings: list[str] = field(default_factory=list)
    risk: str | None = None
    level: int | None = None
    also: list[int] = field(default_factory=list)


@dataclass
class Clustering:
    clusters: list[Cluster]
    home: dict[str, str]                 # node id -> cluster id, for every node a board shows that has a home
    merged_over_limit: int = 0


class _FlowLike:                          # what clustering needs of a flow (board.Flow satisfies it)
    id: str
    path: list[str]
    cause: str | None


def cluster_change(im: ImpactModel, flows: list[_FlowLike], findings: list[Finding], *,
                   is_test: Callable[[str], bool], module_of: Callable[[str], str] | None = None,
                   max_nodes: int = 30, min_changed: int = 3, max_clusters: int = 60) -> Clustering:
    changed = [n for n in im.changed if n in im.nodes]
    chg = set(changed)
    touches: dict[str, set[str]] = defaultdict(set)          # changed function -> fields whose access changed
    for e in im.edges:
        if altered_access(e) and e.src in chg and e.dst in im.nodes:
            touches[e.src].add(e.dst)
    flows_of: dict[str, list[_FlowLike]] = defaultdict(list)
    for f in flows:
        flows_of[f.cause or f.path[-1]].append(f)

    def file_of(n: str) -> str:
        node = im.nodes[n]
        if node.file:
            return node.file
        toucher = next((t for t in sorted(touches, key=_num) if n in touches[t] and im.nodes[t].file), None)
        return im.nodes[toucher].file if toucher else ""

    def required(members: list[str], only: list[_FlowLike] | None = None, fields: bool = True) -> list[str]:
        out: dict[str, None] = dict.fromkeys(members)
        if fields:
            for m in members:
                out.update(dict.fromkeys(sorted(touches.get(m, ()), key=_num)))
        for f in (only if only is not None else [f for m in members for f in flows_of.get(m, [])]):
            out.update(dict.fromkeys(f.path))
        return list(out)

    # 1. join: changed code calling changed code, or sharing a field (test code apart)
    parent = {n: n for n in changed}

    def find(n: str) -> str:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a: str, b: str) -> None:
        if is_test(a) == is_test(b):
            parent[find(a)] = find(b)
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in chg and e.dst in chg:
            union(e.src, e.dst)
    sharers: dict[str, list[str]] = defaultdict(list)
    for fn, fs in touches.items():
        for f in fs:
            sharers[f].append(fn)
            if f in chg:
                union(f, fn)
    for fns in sharers.values():
        for a, b in zip(fns, fns[1:], strict=False):
            union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for n in changed:
        groups[find(n)].append(n)

    # 2. split what doesn't fit
    root = _common_dir([file_of(m) for m in changed if file_of(m)])
    depth = len(root.split("/"))
    module = module_of or (lambda p: posixpath.dirname(p))
    keys: list[Callable[[str], str]] = [lambda n: module(file_of(n)), lambda n: posixpath.dirname(file_of(n)),
                                        file_of]

    def split(members: list[str], level: int = 0) -> list[Cluster]:
        if len(required(members)) <= max_nodes:
            return [Cluster(members=members)]
        for key in keys[level:]:
            level += 1
            parts: dict[str, list[str]] = defaultdict(list)
            for m in members:
                parts[key(m)].append(m)
            if len(parts) > 1:                               # parts under one directory share a board while they fit
                bins: list[tuple[str, list[str]]] = []
                for k, p in sorted(parts.items()):
                    up = posixpath.dirname(k)
                    joinable = key is file_of or len(up.split("/")) > depth     # never two top directories
                    if bins and bins[-1][0] == up and joinable and len(required(bins[-1][1] + p)) <= max_nodes:
                        bins[-1][1].extend(p)
                    else:
                        bins.append((up, list(p)))
                if len(bins) > 1:
                    return [c for _, b in bins for c in split(b, level)]
        packs: list[list[str]] = [[]]                        # one file: pack its functions in source order
        for m in sorted(members, key=lambda n: (im.nodes[n].line or 0, _num(n))):
            if packs[-1] and len(required(packs[-1] + [m])) > max_nodes:
                packs.append([])
            packs[-1].append(m)
        out: list[Cluster] = []
        for p in packs:
            if len(p) > 1 or len(required(p)) <= max_nodes:
                out.append(Cluster(members=p))
            else:
                out.extend(_flow_groups(p[0], flows_of.get(p[0], []), required, max_nodes))   # its board drops fields past 30
        return out

    clusters = [c for g in sorted(groups.values(), key=lambda g: _num(g[0])) for c in split(g)]
    def mem(c: Cluster) -> list[str]:
        return c.members or ([c.of] if c.of else [])
    for c in clusters:
        c.test = all(is_test(m) for m in mem(c))

    def size(c: Cluster) -> int:
        return len(c.required or required(c.members))

    def fns(c: Cluster) -> int:
        return sum(1 for m in c.members if im.nodes[m].kind == "function")

    def home_dir(c: Cluster) -> str:
        return Counter(posixpath.dirname(file_of(m)) for m in c.members).most_common(1)[0][0]

    # 3. merge small clusters into the nearest directory's below the change's root, within the node budget
    merged = True
    while merged:
        merged = False
        for small in sorted([c for c in clusters if c.part is None and fns(c) < min_changed], key=size):
            if small not in clusters:
                continue
            fits = [c for c in clusters if c is not small and c.part is None and c.test == small.test
                    and len(_shared(home_dir(c), home_dir(small))) > depth
                    and len(required(c.members + small.members)) <= max_nodes]
            if fits:                                         # the nearest directory first, then the smallest result
                into = min(fits, key=lambda c: (-len(_shared(home_dir(c), home_dir(small))),
                                                len(required(c.members + small.members)), _num(c.members[0])))
                into.members += small.members
                clusters.remove(small)
                merged = True

    # 4. too many clusters: merge the smallest that share the most directory, past the budget if need be
    over = 0
    while len(clusters) > max_clusters:
        cands = sorted([c for c in clusters if c.part is None], key=size)
        if len(cands) < 2:
            break
        a = cands[0]
        b = max(cands[1:], key=lambda c: (len(_shared(home_dir(a), home_dir(c))), -size(c)))
        b.members += a.members
        clusters.remove(a)
        over += 1

    # flows, required nodes, findings, risk, placement, names, order
    for c in clusters:
        if c.part is None:
            c.flows = [f.id for m in c.members for f in flows_of.get(m, [])]
            c.required = required(c.members)
    home: dict[str, str] = {}
    for c in clusters:
        for m in c.members:
            home.setdefault(m, str(id(c)))
    sev = {f.id: f.severity for f in findings}
    for f in findings:
        owner = next((c for n in f.nodes for c in clusters if n in c.members), None)
        if owner:
            owner.findings.append(f.id)
    for c in clusters:
        c.risk = max((sev[i] for i in c.findings), key=lambda s: SEVERITY_RANK.get(s, 0), default=None)
        levels = Counter(im.nodes[m].layer for m in mem(c) if im.nodes[m].layer is not None)
        c.level = levels.most_common(1)[0][0] if levels else None
        c.also = sorted((lv for lv in levels if lv != c.level), reverse=True)
        c.name = _name([file_of(m) for m in mem(c) if file_of(m)], root)
    names = Counter(c.name for c in clusters if c.part is None)
    for c in clusters:
        main = max(mem(c), key=lambda m: (len(flows_of.get(m, [])), -_num(m)))
        if c.part is not None:
            c.name += f" · {im.nodes[main].label} ({c.part[0]} of {c.part[1]})"
        elif names[c.name] > 1:
            c.name += f" · {im.nodes[main].label}"
    clusters.sort(key=lambda c: (-SEVERITY_RANK.get(c.risk or "", -1), -len(c.flows), -fns(c), c.name))
    rename = {str(id(c)): f"C{i}" for i, c in enumerate(clusters, 1)}
    for i, c in enumerate(clusters, 1):
        c.id = f"C{i}"
    home = {n: rename[k] for n, k in home.items()}
    # nodes without a cluster of their own live where their directory's changed code lives
    by_dir: dict[str, Counter] = defaultdict(Counter)
    for c in clusters:
        for m in c.members:
            by_dir[posixpath.dirname(file_of(m))][c.id] += 1
    for c in clusters:
        for n in c.required:
            if n not in home and file_of(n) and by_dir.get(posixpath.dirname(file_of(n))):
                home[n] = by_dir[posixpath.dirname(file_of(n))].most_common(1)[0][0]
    return Clustering(clusters=clusters, home=home, merged_over_limit=over)


def _flow_groups(m: str, flows: list[_FlowLike], required: Callable, max_nodes: int) -> list[Cluster]:
    """One function that doesn't fit on a board: its flows in groups whose nodes fit (the function is home in the
    first). Its fields don't count here: a board leaves out the fields past its budget."""
    groups: list[list[_FlowLike]] = [[]]
    for f in flows:
        if groups[-1] and len(required([m], groups[-1] + [f], fields=False)) > max_nodes:
            groups.append([])
        groups[-1].append(f)
    n = len(groups)
    if n == 1:
        return [Cluster(members=[m])]
    return [Cluster(members=[m] if i == 0 else [], flows=[f.id for f in g], required=required([m], g), part=(i + 1, n),
                    of=m) for i, g in enumerate(groups)]


def altered_access(e) -> bool:
    """A field access the change added or removed: what joins code and what a board must show."""
    return e.kind in ("writes", "reads") and e.status != "unchanged"


def _name(files: list[str], root: str) -> str:
    """The deepest directory the files share, relative to the change's root; files under several top directories are
    named by each one's deepest shared directory ("deps/reftable + src/libgit2")."""
    rel = [f[len(root):].lstrip("/") if root and f.startswith(root + "/") else f for f in files]
    tops: dict[str, list[str]] = defaultdict(list)
    for f in rel:
        tops[f.split("/")[0] if "/" in f else ""].append(f)
    names = [_common_dir(fs) or posixpath.basename(root) or "." for _, fs in sorted(tops.items())]
    return " + ".join(names[:3]) + (" + …" if len(names) > 3 else "")


def _num(nid: str) -> int:
    return int(nid[1:]) if nid[1:].isdigit() else 0


def _common_dir(paths: list[str]) -> str:
    if not paths:
        return ""
    parts = [p.split("/")[:-1] for p in paths]
    out = []
    for segs in zip(*parts, strict=False):
        if len(set(segs)) != 1:
            break
        out.append(segs[0])
    return "/".join(out)


def _shared(a: str, b: str) -> list[str]:
    out = []
    for x, y in zip(a.split("/"), b.split("/"), strict=False):
        if x != y:
            break
        out.append(x)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_clusters.py -q`
Expected: `15 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `360 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/clusters.py backend/tests/test_clusters.py
git commit -m "feat(board): cluster a large change's changed code"
```

---

### Task 2: An overview and one board per cluster, 30 nodes a board

Spec §2–4, §6. `build_boards` keeps one board when the whole change's required nodes fit in `board_max_nodes` (now
30); otherwise it clusters (Task 1) and builds an `Overview` (the change's about, clusters with counts, files and
node ids, links by calls and shared fields, layers, totals) and one board per cluster with the existing board code:
required nodes first (changed code and flows always; altered fields while they fit, the rest counted as hidden), then
neighbours up to 30 (what its impacts annotate, the fields it uses as before, the most affected code). Nodes that
belong to another cluster are visitors (`home`); every node counts its callers and callees left off the board
(`more_callers`, `more_callees`). Each flow lands on exactly one board; the 12-flow cap is gone. A failure in
clustering falls back to one board and a degraded stage ("shown as one board (clustering failed: …)"). The board stage
stores `board` (single) or `overview`, `board:C<n>` and `node_cluster` (`boardstore.save`, which also tags files);
the AI pass reads one merged board. `fixture_large.build_large_fixture` generates a 6-module C project with two CLs
(201, 202) that needs 7 clusters.

**Files:**
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/store.py`
- Modify: `backend/codetortoise/board.py`
- Create: `backend/codetortoise/boardstore.py`
- Create: `backend/codetortoise/fixture_large.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/tests/test_board.py`
- Test: `backend/tests/test_large_change.py`

**Interfaces:**
- Consumes: `cluster_change`, `altered_access`, `Cluster`, `Clustering` (Task 1).
- Produces: config `analysis.board_max_nodes = 30`, `cluster_min_changed = 3`, `overview_max_clusters = 60`,
  `expand_step = 10` (`max_flows`, `board_blast_nodes` accepted and ignored); `BoardNode.home`, `.more_callers`,
  `.more_callees`; `Flow.cause`; `Board.cluster: ClusterRef(id, name) | None`; `ClusterInfo(id, name, level, also,
  risk, test, files, changed, flows, findings, finding_ids, nodes)`; `ClusterLink(src, dst, calls, fields)`;
  `Overview(about, clusters, links, layers, totals, merged_over_limit)`; dataclass `BoardSet(board, overview, clusters,
  home, note)`; `build_boards(ctx) -> BoardSet`; `Store.delete_blobs(rid, prefix)`, `.blob_keys(rid, prefix)`;
  `boardstore.PREFIX`, `save(store, rid, bs, finding_files)`, `overview(store, rid)`, `board(store, rid, cluster=None)`,
  `boards(store, rid) -> {None: b} | {cid: b}`, `put(store, rid, cluster, b)`, `with_flow(store, rid, flow_id)`,
  `combined(store, rid)`, `merge(parts, about)`; blobs `overview`, `board:C<n>`, `node_cluster`;
  `fixture_large.build_large_fixture(dest) -> FixtureWorkspace`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_board.py`:

```diff
diff --git a/backend/tests/test_board.py b/backend/tests/test_board.py
index 8672fcd..c80a463 100644
--- a/backend/tests/test_board.py
+++ b/backend/tests/test_board.py
@@ -1,6 +1,6 @@
 import pytest
 
-from codetortoise.board import BoardContext, _common_dir, _crossings, _tree_prefix, barycentre_layout, build_board
+from codetortoise.board import BoardContext, _common_dir, _crossings, _tree_prefix, barycentre_layout, build_board, build_boards
 from codetortoise.config import AnalysisConfig
 from codetortoise.detectors.base import DetectorContext, run_detectors
 from codetortoise.diffmap import DiffMap
@@ -273,3 +273,28 @@ def test_flows_stored_without_a_title_get_one_from_their_text():
     assert Flow(path=["N1", "N3"], text="main → logger_flush → uart_send ⟶ -2 ignored", **common).title == "-2 ignored"
     assert Flow(path=["N1", "N3"], text="main → uart_send → Uart::errors → uart_errors", **common).title == \
         "affects uart_errors"
+
+
+def test_fields_whose_access_did_not_change_fill_spare_room_but_never_split_the_review():
+    ctx, _ = _synthetic()
+    for i in range(40):                                       # set() also reads 40 fields, as it did before the change
+        nid = f"N{10 + i}"
+        ctx.impact.nodes[nid] = Node(id=nid, key=f"field:c:@S@R@FI@f{i}", kind="field", label=f"R::f{i}", layer=1)
+        ctx.impact.edges.append(Edge(id=f"E{100 + i}", src="N1", dst=nid, kind="reads"))
+    bs = build_boards(ctx)
+    assert bs.overview is None and len(bs.board.nodes) <= 30
+    assert any(n.label.startswith("R::f") for n in bs.board.nodes)
+
+
+def test_a_board_leaves_out_fields_past_the_budget_but_never_changed_code_or_flows():
+    ctx, _ = _synthetic()
+    for i in range(40):                                       # set() newly writes 40 more fields
+        nid = f"N{10 + i}"
+        ctx.impact.nodes[nid] = Node(id=nid, key=f"field:c:@S@R@FI@f{i}", kind="field", label=f"R::f{i}", layer=1)
+        ctx.impact.edges.append(Edge(id=f"E{100 + i}", src="N1", dst=nid, kind="writes", status="added"))
+    bs = build_boards(ctx)
+    boards = [bs.board] if bs.board else list(bs.clusters.values())
+    assert all(len(b.nodes) <= 30 for b in boards)
+    (b,) = boards
+    flow_nodes = {n for f in b.flows for n in f.path}
+    assert "N1" in {n.id for n in b.nodes} and flow_nodes <= {n.id for n in b.nodes} and b.hidden_nodes >= 11
```

`backend/tests/test_large_change.py`:

```python
"""A large change is split into clusters with an overview (spec 2026-10-03-large-change-boards), end to end."""
import pytest
from helpers import make_services

from codetortoise import boardstore
from codetortoise.fixture_large import build_large_fixture
from codetortoise.pipeline import run_review


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    d = tmp_path_factory.mktemp("large")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    rid = svc.store.create_review("large", "owner", fx.cls)
    run_review(rid, svc)
    return svc, rid


def test_a_large_change_gets_an_overview_and_a_board_per_cluster(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    assert ov is not None and boardstore.board(svc.store, rid) is None              # no single board
    assert {c.name for c in ov.clusters} == {"app/telemetry", "drv/dma", "drv/uart", "hal/regs", "svc/logger",
                                             "svc/stats", "tests"}
    assert [c.id for c in ov.clusters] == [f"C{i}" for i in range(1, len(ov.clusters) + 1)]
    assert ov.clusters[-1].name == "tests"                                          # least risky last
    boards = boardstore.boards(svc.store, rid)
    assert set(boards) == {c.id for c in ov.clusters}
    assert all(len(b.nodes) <= 30 for b in boards.values())
    stage = next(s for s in svc.store.list_stages(rid) if s["name"] == "board")
    assert stage["status"] == "ok" and "7 cluster board(s)" in stage["message"]


def test_every_changed_function_and_flow_is_on_exactly_one_board(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    im = svc.store.get_blob(rid, "impact")
    homes = [n for c in ov.clusters for n in c.nodes]
    assert sorted(homes) == sorted(im["changed"]) and len(homes) == len(set(homes))
    flows = [f.id for b in boardstore.boards(svc.store, rid).values() for f in b.flows]
    assert len(flows) == len(set(flows)) == ov.totals["flows"]
    node_cluster = svc.store.get_blob(rid, "node_cluster")
    assert all(node_cluster[n] == c.id for c in ov.clusters for n in c.nodes)


def test_cluster_boards_mark_visitors_and_link_clusters(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    regs = next(c for c in ov.clusters if c.name == "hal/regs")
    b = boardstore.board(svc.store, rid, regs.id)
    assert b.cluster.id == regs.id and b.cluster.name == "hal/regs"
    visitors = [n for n in b.nodes if n.home]
    assert visitors and all(n.home != regs.id for n in visitors)
    assert {n.label for n in b.nodes if n.change and not n.home} == {"regs_a1", "regs_a2", "regs_a3", "regs_b1",
                                                                     "regs_b2"}
    uart = next(c for c in ov.clusters if c.name == "drv/uart")
    assert any(l.src == uart.id and l.dst == regs.id and l.calls > 0 for l in ov.links)      # uart calls into regs
    assert {f.path.split("/")[-2] for d in b.about.tree for f in d.files} == {"regs"}         # its own files only


def test_nodes_with_neighbours_off_the_board_say_how_many(large):
    svc, rid = large
    boards = boardstore.boards(svc.store, rid)
    assert any(n.more_callers > 0 for b in boards.values() for n in b.nodes)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_board.py tests/test_large_change.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_boards' from 'codetortoise.board'` and `cannot import name 'boardstore' from 'codetortoise'` (collection stops: `2 errors`)

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 470c6f7..89775b9 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -86,9 +86,12 @@ class AnalysisConfig(BaseModel):
     workers: int = 4
     index_scope: Literal["compile_db", "workspace"] = "compile_db"   # files the symbol index parses
     heuristic_fanin_cap: int = 50  # names with more out-of-TU callers/refs than this are not expanded heuristically
-    max_flows: int = 12            # review board: flows listed (entry -> change -> where the effect lands)
-    board_max_nodes: int = 150     # review board: functions/fields drawn
-    board_blast_nodes: int = 60    # review board: top blast-radius functions included
+    max_flows: int = 12            # accepted and ignored: a board's node budget bounds its flows
+    board_max_nodes: int = 30      # nodes a board draws before the reader expands it; larger changes are split
+    board_blast_nodes: int = 60    # accepted and ignored (neighbours fill a board's budget)
+    cluster_min_changed: int = 3   # clusters with fewer changed functions merge with one in the same directory
+    overview_max_clusters: int = 60  # more clusters than this: the smallest merge further
+    expand_step: int = 10          # "+N callers / callees": neighbours added per expansion
     entrypoint_patterns: list[str] = Field(
         default_factory=lambda: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"])
 
```

`backend/codetortoise/store.py`:

```diff
diff --git a/backend/codetortoise/store.py b/backend/codetortoise/store.py
index b18ec92..6bc005e 100644
--- a/backend/codetortoise/store.py
+++ b/backend/codetortoise/store.py
@@ -143,6 +143,14 @@ class Store:
     def put_blob(self, rid: int, key: str, obj: Any) -> None:
         self._exec("INSERT OR REPLACE INTO blobs(review_id, key, json) VALUES(?,?,?)", (rid, key, _dump(obj)))
 
+    def delete_blobs(self, rid: int, prefix: str) -> None:
+        """Remove the review's blobs whose key starts with `prefix` (a re-run's old cluster boards)."""
+        self._exec("DELETE FROM blobs WHERE review_id=? AND substr(key, 1, ?)=?", (rid, len(prefix), prefix))
+
+    def blob_keys(self, rid: int, prefix: str) -> list[str]:
+        return [r["key"] for r in self._all("SELECT key FROM blobs WHERE review_id=? AND substr(key, 1, ?)=? ORDER BY key",
+                                            (rid, len(prefix), prefix))]
+
     def get_blob(self, rid: int, key: str) -> Any:
         rows = self._all("SELECT json FROM blobs WHERE review_id=? AND key=?", (rid, key))
         return json.loads(rows[0]["json"]) if rows else None
```

`backend/codetortoise/board.py`:

```diff
diff --git a/backend/codetortoise/board.py b/backend/codetortoise/board.py
index 727adb4..b7c5934 100644
--- a/backend/codetortoise/board.py
+++ b/backend/codetortoise/board.py
@@ -12,10 +12,12 @@ import re
 from collections import defaultdict, deque
 from collections.abc import Callable
 from dataclasses import dataclass
+from dataclasses import field as dfield
 from typing import Literal
 
 from pydantic import BaseModel, Field, model_validator
 
+from codetortoise.clusters import altered_access, cluster_change
 from codetortoise.config import AnalysisConfig
 from codetortoise.detectors.base import SEVERITY_RANK, Finding
 from codetortoise.diffmap import DiffMap
@@ -58,6 +60,9 @@ class BoardNode(BaseModel):
     x: float = 0.0
     warn: int = 0
     files: Files = None
+    home: str | None = None          # a visitor: the cluster this node belongs to (spec 2026-10-03-large §3)
+    more_callers: int = 0            # callers / callees not on the board, for "+N callers" (expansion)
+    more_callees: int = 0
 
 
 class BoardEdge(BaseModel):
@@ -99,6 +104,7 @@ class Flow(BaseModel):
     effect: str
     check: str
     what_source: Literal["template", "llm"] = "template"
+    cause: str | None = None         # the changed node the flow comes from (its cluster's)
     files: Files = None
     what_files: Files = None         # files behind `what`/`title`: the flow's own for template text, the prompt's for LLM text
 
@@ -182,6 +188,11 @@ class About(BaseModel):
     drift: list[AboutDrift] = Field(default_factory=list)   # base workspace differs from the CL base: context code may not match
 
 
+class ClusterRef(BaseModel):
+    id: str
+    name: str
+
+
 class Board(BaseModel):
     nodes: list[BoardNode] = Field(default_factory=list)
     edges: list[BoardEdge] = Field(default_factory=list)
@@ -190,6 +201,47 @@ class Board(BaseModel):
     layers: list[BoardLayer] = Field(default_factory=list)
     about: About
     hidden_nodes: int = 0
+    cluster: ClusterRef | None = None   # a cluster's board in a split review
+
+
+class ClusterInfo(BaseModel):
+    id: str
+    name: str
+    level: int | None = None
+    also: list[int] = Field(default_factory=list)
+    risk: str | None = None
+    test: bool = False
+    files: list[str] = Field(default_factory=list)    # depot paths of its changed code
+    changed: int = 0                                  # changed functions
+    flows: int = 0
+    findings: int = 0
+    nodes: list[str] = Field(default_factory=list)    # its changed nodes
+
+
+class ClusterLink(BaseModel):
+    src: str
+    dst: str
+    calls: int = 0                                    # calls from src's changed code into dst's
+    fields: int = 0                                   # fields src's changed code writes and dst's reads or writes
+
+
+class Overview(BaseModel):
+    about: About
+    clusters: list[ClusterInfo] = Field(default_factory=list)
+    links: list[ClusterLink] = Field(default_factory=list)
+    layers: list[BoardLayer] = Field(default_factory=list)
+    totals: dict[str, int] = Field(default_factory=dict)
+    merged_over_limit: int = 0
+
+
+@dataclass
+class BoardSet:
+    """What the board stage stores: one board, or an overview and one board per cluster."""
+    board: Board | None = None
+    overview: Overview | None = None
+    clusters: dict[str, Board] = dfield(default_factory=dict)
+    home: dict[str, str] = dfield(default_factory=dict)     # node id -> cluster id
+    note: str | None = None                                # why the review fell back to one board
 
 
 @dataclass
@@ -256,6 +308,15 @@ class _Ctx:
         for f in c.findings:
             for n in f.nodes:
                 self.finding_by[(f.kind, n)].append(f.id)
+        self.record_file = {f"field:{a.field}": a.record_file for a in self.fields_before + self.fields_after
+                            if a.record_file}
+        self.decl_line = {f"field:{a.field}": a.decl_line for a in self.fields_before + self.fields_after if a.decl_line}
+        self.callers: dict[str, set[str]] = defaultdict(set)
+        self.callees: dict[str, set[str]] = defaultdict(set)
+        for e in c.impact.edges:
+            if e.kind in ("call", "virtual"):
+                self.callers[e.dst].add(e.src)
+                self.callees[e.src].add(e.dst)
 
     def is_test(self, nid: str) -> bool:
         """Test code is never a flow entry or landing, and is not shown as blast radius."""
@@ -268,6 +329,37 @@ class _Ctx:
     def label(self, nid: str) -> str:
         return self.im.nodes[nid].label
 
+    def is_test_path(self, nid: str) -> bool:
+        """Test code by path, changed or not (clusters keep changed test code apart)."""
+        f = self.im.nodes[nid].file
+        if not f:
+            return False
+        root = self.c.root.rstrip("/") + "/"
+        return is_test_path(f[len(root):] if self.c.root and f.startswith(root) else f)
+
+    def module_of(self, path: str) -> str:
+        return self.c.layers.module_of(path) if self.c.layers and path else posixpath.dirname(path)
+
+    def local(self, nid: str) -> str | None:
+        """The node's file: a field's record header, a function's file (after side first)."""
+        n = self.im.nodes[nid]
+        if n.kind == "field":
+            return self.record_file.get(n.key) or None
+        fn = self.fa.get(n.key) or self.fb.get(n.key)
+        return fn.file if fn else n.file
+
+    def layer(self, nid: str) -> int:
+        """Its layer band: fields sit in their record's module's layer, else their writer's; -1 for none."""
+        n = self.im.nodes[nid]
+        lv = n.layer
+        if n.kind == "field":
+            rf = self.record_file.get(n.key)
+            lv = self.c.layers.level_of(rf) if (self.c.layers and rf) else None
+            if lv is None:
+                lv = next((self.im.nodes[e.src].layer for e in self.im.edges if e.dst == nid and e.kind == "writes"
+                           and self.im.nodes[e.src].layer is not None), None)
+        return lv if lv is not None else -1
+
     def finding(self, kind: str, nid: str) -> str | None:
         ids = self.finding_by.get((kind, nid))
         return ids[0] if ids else None
@@ -488,9 +580,8 @@ def build_flows(x: _Ctx, impacts: list[Impact]) -> list[Flow]:
         sev = sev_of.get(imp.finding or "", "medium")
         flows.append(Flow(id="", path=path, tag=tag, lands=land, fx_at=fx_at, severity=sev,
                           findings=[imp.finding] if imp.finding else [], text=text, title=title, what=what, effect=effect,
-                          check=check))
+                          check=check, cause=cause))
     flows.sort(key=lambda f: (-SEVERITY_RANK.get(f.severity, 0), 0 if f.tag == "state" else 1, len(f.path), f.text))
-    flows = flows[: x.c.cfg.max_flows]
     for i, f in enumerate(flows):
         f.id = f"FL{i + 1}"
     return flows
@@ -543,73 +634,68 @@ def barycentre_layout(layer_of: dict[str, int], edges: list[tuple[str, str]], sw
     return xs
 
 
-def build_board(c: BoardContext) -> Board:
-    x = _Ctx(c)
-    impacts = build_impacts(x)
-    flows = build_flows(x, impacts)
-    im = c.impact
-    # node selection: changed, flow nodes, fields around changed functions, then top blast items; capped
-    chosen: list[str] = []
-
-    def take(nid):
-        if nid in im.nodes and nid not in chosen:
-            chosen.append(nid)
-    for n in im.changed:
-        take(n)
+def _required(x: _Ctx, members: list[str], flows: list[Flow], fields: bool = True) -> list[str]:
+    """Nodes a board must show, in this order: its changed code, every node on its flows, and the fields whose access
+    its changed code added or removed (left out past the budget when one function touches too many)."""
+    out: dict[str, None] = dict.fromkeys(n for n in members if n in x.im.nodes)
     for f in flows:
-        for n in f.path:
-            take(n)
-    for e in im.edges:
-        if e.kind in ("writes", "reads") and e.src in x.changed:
-            take(e.dst)
+        out.update(dict.fromkeys(n for n in f.path if n in x.im.nodes))
+    for e in x.im.edges if fields else ():
+        if altered_access(e) and e.src in out and e.src in x.changed and e.dst in x.im.nodes:
+            out.setdefault(e.dst)
+    return list(out)
+
+
+def _neighbours(x: _Ctx, impacts: list[Impact], scope: set[str]) -> list[str]:
+    """Unchanged code worth showing beside `scope`'s changes, most relevant first: what its impacts annotate, the fields
+    it touches, then the most affected code (blast radius) reached from it."""
+    out: dict[str, None] = {}
     for i in impacts:
-        if not x.is_test(i.node):
-            take(i.node)
-    for b in [b for b in im.blast if not x.is_test(b.node)][: c.cfg.board_blast_nodes]:
-        take(b.node)
-    hidden = max(0, len(chosen) - c.cfg.board_max_nodes)
-    chosen = chosen[: c.cfg.board_max_nodes]
+        if i.cause in scope and i.node in x.im.nodes and not x.is_test(i.node):
+            out.setdefault(i.node)
+    for e in x.im.edges:                                  # fields the changed code touches as it did before
+        if e.kind in ("writes", "reads") and e.src in scope and e.src in x.changed and e.dst in x.im.nodes:
+            out.setdefault(e.dst)
+    for b in x.im.blast:
+        if b.path and b.path[-1] in scope and not x.is_test(b.node):
+            out.setdefault(b.node)
+    return list(out)
+
+
+def _choose(x: _Ctx, required: list[str], neighbours: list[str], core: int = 0) -> tuple[list[str], int]:
+    """The required nodes, then neighbours up to the board's budget; how many nodes were left out. The first `core`
+    required nodes (changed code and flows) always stay; the fields after them only while they fit."""
+    budget = x.c.cfg.board_max_nodes
+    chosen = required[:max(budget, core)]
+    rest = [n for n in neighbours if n not in set(required)]
+    room = max(0, budget - len(chosen))
+    return chosen + rest[:room], len(required) - len(chosen) + max(0, len(rest) - room)
+
+
+def _render(x: _Ctx, impacts: list[Impact], flows: list[Flow], chosen: list[str], depots: dict[str, str], *,
+            hidden: int, about: About, cluster: ClusterRef | None = None, home: dict[str, str] | None = None) -> Board:
+    """Lay out and describe the chosen nodes as a board."""
+    c, im = x.c, x.im
     sel = set(chosen)
-    # layers: fields sit in the layer of their record's module, else their writer's layer
-    # after-side facts win: the node shows the new file
-    record_file = {f"field:{a.field}": a.record_file for a in x.fields_before + x.fields_after if a.record_file}
-    decl_line = {f"field:{a.field}": a.decl_line for a in x.fields_before + x.fields_after if a.decl_line}
-    layer_of: dict[str, int] = {}
-    for nid in chosen:
-        n = im.nodes[nid]
-        lv = n.layer
-        if n.kind == "field":
-            rf = record_file.get(n.key)
-            lv = c.layers.level_of(rf) if (c.layers and rf) else None
-            if lv is None:
-                lv = next((im.nodes[e.src].layer for e in im.edges if e.dst == nid and e.kind == "writes"
-                           and im.nodes[e.src].layer is not None), None)
-        layer_of[nid] = lv if lv is not None else -1
+    layer_of = {nid: x.layer(nid) for nid in chosen}
     edges = [e for e in im.edges if e.src in sel and e.dst in sel]
     xs = barycentre_layout(layer_of, [(e.src, e.dst) for e in edges])
-    # per-node details
     warn = defaultdict(int)
     for i in impacts:
         if i.severity == "warn":
             warn[i.node] += 1
     kind_of = {"body_modified": "modified", "signature_changed": "signature", "added": "added", "removed": "removed"}
     texts = {f.local: f for f in c.cs.files}
-    shown = [i for i in impacts if i.node in sel]
-    locals_of: dict[str, str | None] = {}
-    for nid in chosen:
-        n = im.nodes[nid]
-        fn = x.fa.get(n.key) or x.fb.get(n.key)
-        locals_of[nid] = (record_file.get(n.key) or None) if n.kind == "field" else (fn.file if fn else n.file)
-    depots = c.depots_for(sorted({p for p in [*locals_of.values(), *(i.path for i in shown)] if p}))
+    shown = [i.model_copy() for i in impacts if i.node in sel]
     for i in shown:
         i.path = depots.get(i.path) if i.path else None
     nodes = []
     for nid in chosen:
         n = im.nodes[nid]
         fn = x.fa.get(n.key) or x.fb.get(n.key)
-        local, rng, change = locals_of[nid], None, None
+        local, rng, change = x.local(nid), None, None
         if n.kind == "field":
-            dl = decl_line.get(n.key)
+            dl = x.decl_line.get(n.key)
             rng = [dl, dl] if dl else None
         elif fn is not None:
             rng = [fn.start_line, fn.end_line]
@@ -620,15 +706,114 @@ def build_board(c: BoardContext) -> Board:
             if fc is not None:
                 add, rem = _count(fc.before, fc.after, fn.start_line, fn.end_line)
             change = NodeChange(kind=kind_of.get(ch.kind if ch else "", "modified"), add=add, rem=rem)
+        callers = {s_ for s_ in x.callers.get(nid, ()) if s_ not in sel and not x.is_test(s_)}
+        callees = {d for d in x.callees.get(nid, ()) if d not in sel and not x.is_test(d)}
+        h = (home or {}).get(nid)
         nodes.append(BoardNode(id=nid, key=n.key, label=n.label, kind=n.kind, layer=layer_of[nid],
                                path=depots.get(local) if local else None, local=local, range=rng, change=change,
-                               x=xs.get(nid, 0.0), warn=warn[nid]))
+                               x=xs.get(nid, 0.0), warn=warn[nid], home=h if cluster and h and h != cluster.id else None,
+                               more_callers=len(callers), more_callees=len(callees)))
     levels = sorted({lv for lv in layer_of.values()}, reverse=True)
     layers = [BoardLayer(level=lv, name=(_layer_name(x, lv) if lv >= 0 else "other")) for lv in levels]
     return Board(nodes=nodes, edges=[BoardEdge(src=e.src, dst=e.dst, kind=e.kind, status=e.status, confidence=e.confidence)
                                      for e in edges],
-                 flows=flows, impacts=shown, layers=layers,
-                 about=build_about(c), hidden_nodes=hidden)
+                 flows=flows, impacts=shown, layers=layers, about=about, hidden_nodes=hidden, cluster=cluster)
+
+
+def build_board(c: BoardContext) -> Board:
+    """One board for the whole change, within the node budget: required nodes first (changed code, flows, fields),
+    then neighbours. Large changes use `build_boards`, which splits them; this is also its fallback."""
+    x = _Ctx(c)
+    impacts = build_impacts(x)
+    flows = build_flows(x, impacts)
+    req = _required(x, list(x.im.changed), flows)
+    chosen, hidden = _choose(x, req, _neighbours(x, impacts, set(x.changed)), core=len(req))   # trimmed below
+    if len(chosen) > c.cfg.board_max_nodes:                 # the fallback: the most important nodes only
+        hidden += len(chosen) - c.cfg.board_max_nodes
+        chosen = chosen[: c.cfg.board_max_nodes]
+        sel = set(chosen)
+        flows = [f for f in flows if set(f.path) <= sel]
+    sel = set(chosen)
+    depots = c.depots_for(sorted({p for p in [*(x.local(n) for n in chosen), *(i.path for i in impacts if i.node in sel)]
+                                  if p}))
+    return _render(x, impacts, flows, chosen, depots, hidden=hidden, about=build_about(c))
+
+
+def build_boards(c: BoardContext) -> BoardSet:
+    """The change's board, or (when it would need more than `board_max_nodes` nodes) an overview and one board per
+    cluster (spec 2026-10-03-large-change-boards). Every changed node and flow is on exactly one board."""
+    x = _Ctx(c)
+    impacts = build_impacts(x)
+    flows = build_flows(x, impacts)
+    if len(_required(x, list(x.im.changed), flows)) <= c.cfg.board_max_nodes:
+        return BoardSet(board=build_board(c))
+    try:
+        res = cluster_change(x.im, flows, c.findings, is_test=x.is_test_path, module_of=x.module_of,
+                             max_nodes=c.cfg.board_max_nodes, min_changed=c.cfg.cluster_min_changed,
+                             max_clusters=c.cfg.overview_max_clusters)
+    except Exception as e:  # never lose the review over clustering: one board of the most important nodes
+        return BoardSet(board=build_board(c), note=f"shown as one board (clustering failed: {type(e).__name__}: {e})")
+    by_id = {f.id: f for f in flows}
+    picks = {}
+    for cl in res.clusters:
+        cf = [by_id[i] for i in cl.flows]
+        mem = cl.members or ([cl.of] if cl.of else [])
+        req, core = _required(x, mem, cf), len(_required(x, mem, cf, fields=False))
+        picks[cl.id] = (cf, *_choose(x, req, _neighbours(x, impacts, set(cl.members)), core))
+    shown = {n for _, chosen, _ in picks.values() for n in chosen}
+    locals_ = {x.local(n) for n in shown} | {i.path for i in impacts if i.node in shown}
+    locals_ |= {x.local(m) for cl in res.clusters for m in cl.members}
+    depots = c.depots_for(sorted(p for p in locals_ if p))
+    about = build_about(c)
+    boards = {}
+    for cl in res.clusters:
+        cf, chosen, hidden = picks[cl.id]
+        files = {depots.get(x.local(m)) for m in (cl.members or [cl.of]) if x.local(m)} - {None}   # its own code
+        mine = set(cl.findings)
+        part = about.model_copy(deep=True)
+        part.tree = [AboutDir(dir=d.dir, files=[f for f in d.files if f.path in files]) for d in part.tree]
+        part.tree = [d for d in part.tree if d.files]
+        part.why = [w for w in part.why if w.finding in mine] or [AboutWhy(severity=f.severity, text=f.title, finding=f.id)
+                                                                   for f in c.findings if f.id in mine][:4]
+        part.drift = [d for d in part.drift if set(d.files or []) & files]
+        boards[cl.id] = _render(x, impacts, cf, chosen, depots, hidden=hidden, about=part,
+                                cluster=ClusterRef(id=cl.id, name=cl.name), home=res.home)
+    return BoardSet(overview=_overview(x, res, about, depots, flows), clusters=boards, home=res.home)
+
+
+def _overview(x: _Ctx, res, about: About, depots: dict[str, str], flows: list[Flow]) -> Overview:
+    infos = []
+    for cl in res.clusters:
+        infos.append(ClusterInfo(
+            id=cl.id, name=cl.name, level=cl.level, also=cl.also, risk=cl.risk, test=cl.test,
+            files=sorted({depots[x.local(m)] for m in cl.members if x.local(m) in depots}),
+            changed=sum(1 for m in cl.members if x.im.nodes[m].kind == "function"), flows=len(cl.flows),
+            findings=len(cl.findings), nodes=list(cl.members)))
+    owner = {m: cl.id for cl in res.clusters for m in cl.members}
+    calls: dict[tuple[str, str], int] = defaultdict(int)
+    for e in x.im.edges:
+        a, b = owner.get(e.src), owner.get(e.dst)
+        if e.kind in ("call", "virtual") and a and b and a != b:
+            calls[(a, b)] += 1
+    writes: dict[str, set[str]] = defaultdict(set)
+    touches: dict[str, set[str]] = defaultdict(set)
+    for e in x.im.edges:
+        cid = owner.get(e.src)
+        if cid and e.kind in ("writes", "reads"):
+            touches[cid].add(e.dst)
+            if e.kind == "writes":
+                writes[cid].add(e.dst)
+    shared = {(a, b): len(writes[a] & touches[b]) for a in writes for b in touches if a != b}
+    links = [ClusterLink(src=a, dst=b, calls=calls.get((a, b), 0), fields=shared.get((a, b), 0))
+             for a, b in sorted(set(calls) | {k for k, v in shared.items() if v})]
+    levels = sorted({cl.level if cl.level is not None else -1 for cl in res.clusters}
+                    | {lv for cl in res.clusters for lv in cl.also}, reverse=True)
+    layers = [BoardLayer(level=lv, name=(_layer_name(x, lv) if lv >= 0 else "other")) for lv in levels]
+    totals = {"files": len(about.tree and [f for d in about.tree for f in d.files]), "clusters": len(res.clusters),
+              "flows": len(flows), "findings": len(x.c.findings),
+              "changed": sum(1 for n in x.im.changed if n in x.im.nodes and x.im.nodes[n].kind == "function")}
+    return Overview(about=about, clusters=infos, links=links, layers=layers, totals=totals,
+                    merged_over_limit=res.merged_over_limit)
 
 
 def _tree_prefix(depots: list[str]) -> str:
```

`backend/codetortoise/boardstore.py`:

```python
"""Where a review's boards live (spec 2026-10-03-large-change-boards §4).

A review that fits on one board has the blob `board`. A split review has `overview`, one `board:C<n>` per cluster and
`node_cluster` (node id -> cluster id). Everything that reads or rewrites boards (the pipeline's AI pass, on-demand
explanations, the API) goes through here.
"""
from __future__ import annotations

from codetortoise.board import Board, BoardSet, Files, Overview
from codetortoise.provenance import tag_board
from codetortoise.store import Store

PREFIX = "board:"


def save(store: Store, rid: int, bs: BoardSet, finding_files: dict[str, Files]) -> None:
    """Store a board stage's result, replacing whatever an earlier run stored."""
    store.delete_blobs(rid, PREFIX)
    for key in ("board", "overview", "node_cluster"):
        store.delete_blobs(rid, key)
    if bs.board is not None:
        store.put_blob(rid, "board", tag_board(bs.board, finding_files))
        return
    store.put_blob(rid, "overview", bs.overview)
    store.put_blob(rid, "node_cluster", bs.home)
    for cid, b in bs.clusters.items():
        store.put_blob(rid, PREFIX + cid, tag_board(b, finding_files))


def overview(store: Store, rid: int) -> Overview | None:
    o = store.get_blob(rid, "overview")
    return Overview.model_validate(o) if o else None


def board(store: Store, rid: int, cluster: str | None = None) -> Board | None:
    raw = store.get_blob(rid, PREFIX + cluster if cluster else "board")
    return Board.model_validate(raw) if raw else None


def boards(store: Store, rid: int) -> dict[str | None, Board]:
    """Every board of the review: {None: board} for one board, {cluster id: board} for a split review."""
    single = board(store, rid)
    if single is not None:
        return {None: single}
    keys = sorted(store.blob_keys(rid, PREFIX), key=lambda k: int(k[len(PREFIX) + 1:]))
    return {k[len(PREFIX):]: Board.model_validate(store.get_blob(rid, k)) for k in keys}


def put(store: Store, rid: int, cluster: str | None, b: Board) -> None:
    store.put_blob(rid, PREFIX + cluster if cluster else "board", b)


def with_flow(store: Store, rid: int, flow_id: str) -> tuple[str | None, Board] | None:
    """The board holding a flow (each flow is on exactly one board)."""
    for key, b in boards(store, rid).items():
        if any(f.id == flow_id for f in b.flows):
            return key, b
    return None


def combined(store: Store, rid: int) -> Board | None:
    """One board standing for the whole review, for AI prompts: the single board, or the overview's summary with every
    cluster's nodes, flows (in review order) and annotations. Its flows are the stored boards' own objects."""
    bs = boards(store, rid)
    if None in bs:
        return bs[None]
    if not bs:
        return None
    ov = overview(store, rid)
    return merge(list(bs.values()), ov.about if ov else next(iter(bs.values())).about)


def merge(parts: list[Board], about) -> Board:
    nodes, seen = [], set()
    for b in parts:
        for n in b.nodes:
            if n.id not in seen:
                seen.add(n.id)
                nodes.append(n)
    flows = sorted((f for b in parts for f in b.flows), key=lambda f: int(f.id[2:]) if f.id[2:].isdigit() else 0)
    return Board(nodes=nodes, edges=[e for b in parts for e in b.edges], flows=flows,
                 impacts=[i for b in parts for i in b.impacts], layers=parts[0].layers if parts else [], about=about)
```

`backend/codetortoise/fixture_large.py`:

```python
"""A generated C project large enough to need an overview and cluster boards (spec 2026-10-03-large-change-boards §8).

Six modules in four layers (hal, drv, svc, app), each a header and four source files, plus tests. CL 201 makes
changes across the stack: new return values that callers ignore, and new writes to fields other code reads. CL 202
changes the tests and one service function. Like the bundled fixture, it is a git workspace whose CLs are commits.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from codetortoise.fixture import FixtureWorkspace

# (directory, module, the module it calls into)
MODULES = [("hal/regs", "regs", None), ("drv/uart", "uart", "regs"), ("drv/dma", "dma", "regs"),
           ("svc/logger", "logger", "uart"), ("svc/stats", "stats", "dma"), ("app/telemetry", "telem", "logger")]
FILES = "abcd"
FNS = 5
CL_DESCRIPTIONS = {201: "stats: count transmit errors across the stack", 202: "tests: cover the new error counts"}
CHANGED = {"a": (1, 2, 3), "b": (1, 2)}     # file -> functions CL 201 changes in every module


def _fn(mod: str, f: str, i: int) -> str:
    return f"{mod}_{f}{i}"


def _header(mod: str, low: str | None) -> str:
    protos = "\n".join(f"int {_fn(mod, f, i)}(int v);" for f in FILES for i in range(1, FNS + 1))
    inc = f'#include "{low}.h"\n' if low else ""
    t = mod.capitalize()
    return (f"#ifndef {mod.upper()}_H\n#define {mod.upper()}_H\n{inc}\nstruct {t}Dev {{\n\tint count;\n\tint errors;\n"
            f"\tint state;\n\tint last;\n}};\n\nextern struct {t}Dev {mod}_dev;\n\n{protos}\n\n#endif\n")


def _source(mod: str, low: str | None, f: str, changed: bool) -> str:
    out = [f'#include "{mod}.h"\n']
    if f == "a":
        out.append(f"struct {mod.capitalize()}Dev {mod}_dev;\n")
    for i in range(1, FNS + 1):
        name = _fn(mod, f, i)
        body = []
        if low:
            callee = _fn(low, f, i)
            # odd functions ignore what the lower layer returns (a contract flow lands there when it changes)
            body.append(f"\t{callee}(v);" if i % 2 else f"\tint r = {callee}(v);\n\tif (r < 0)\n\t\treturn r;")
        if f == "d":
            body.append(f"\treturn {mod}_dev.errors + {mod}_dev.last;")       # readers: state flows land here
        else:
            body.append(f"\t{mod}_dev.count += 1;")
            if changed and i in CHANGED.get(f, ()):
                body.append(f"\tif (v > 100) {{\n\t\t{mod}_dev.errors = v;\n\t\t{mod}_dev.last = {i};\n\t\treturn -2;\n\t}}")
            body.append("\tif (v < 0)\n\t\treturn -1;\n\treturn 0;")
        out.append(f"int {name}(int v)\n{{\n" + "\n".join(body) + "\n}\n")
    return "\n".join(out)


def _tests(changed: bool) -> str:
    lines = ['#include "uart.h"', '#include "stats.h"', "", "int test_uart(void)", "{", "\tif (uart_a1(1) != 0)",
             "\t\treturn 1;"]
    if changed:
        lines += ["\tif (uart_a1(101) != -2)", "\t\treturn 2;", "\tif (stats_a2(101) != -2)", "\t\treturn 3;"]
    lines += ["\treturn 0;", "}", ""]
    return "\n".join(lines)


def _write(root: Path, changed: int) -> None:
    for d, mod, low in MODULES:
        (root / "include").mkdir(parents=True, exist_ok=True)
        (root / "include" / f"{mod}.h").write_text(_header(mod, low))
        (root / d).mkdir(parents=True, exist_ok=True)
        for f in FILES:
            ch = changed >= 201 and (mod != "stats" or changed >= 202 or f != "b")
            (root / d / f"{mod}_{f}.c").write_text(_source(mod, low, f, ch))
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_uart.c").write_text(_tests(changed >= 202))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def build_large_fixture(dest: Path) -> FixtureWorkspace:
    root = Path(dest) / "ws"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write(root, 0)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    for cl, desc in sorted(CL_DESCRIPTIONS.items()):
        _write(root, cl)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"CL {cl}: {desc}")
    _git(root, "checkout", "-q", base)
    entries = [{"directory": str(root), "file": str(src),
                "arguments": ["clang", "-xc", "-Iinclude", "-c", str(src), "-o", str(src.with_suffix(".o"))]}
               for src in sorted(root.rglob("*.c")) if ".git" not in src.parts]
    cc = root / "compile_commands.json"
    cc.write_text(json.dumps(entries, indent=2))
    return FixtureWorkspace(root=root, compile_commands=cc, cls=sorted(CL_DESCRIPTIONS))
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index c726b34..6b9b59f 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -9,7 +9,8 @@ from collections.abc import Callable
 from concurrent.futures import ThreadPoolExecutor
 from pathlib import Path
 
-from codetortoise.board import BoardContext, build_board
+from codetortoise import boardstore
+from codetortoise.board import BoardContext, build_boards
 from codetortoise.detectors.base import DetectorContext, run_detectors
 from codetortoise.diffmap import map_changes
 from codetortoise.facts.model import Facts
@@ -17,7 +18,7 @@ from codetortoise.facts.runner import build_requests, parse_summary, run_extract
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import build_storyboard
 from codetortoise.paths import canon
-from codetortoise.provenance import finding_files, impact_node_files, local_files, tag_board
+from codetortoise.provenance import finding_files, impact_node_files, local_files
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
@@ -216,8 +217,8 @@ def run_review(rid: int, svc: Services) -> None:
     def board():
         notes: list[str] = []
         resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
-        b = build_board(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
-                                     ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root))))
+        bs = build_boards(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
+                                       ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root))))
         # file tags (spec §14.3): every graph node and finding, from one more lookup of the files not yet resolved
         findings, im = ctx["findings"], ctx["impact"]
         decl = {f"field:{a.field}": a.record_file for fx in ctx["before"] + ctx["after"] for a in fx.fields if a.record_file}
@@ -230,24 +231,30 @@ def run_review(rid: int, svc: Services) -> None:
         store.put_findings(rid, findings)
         ctx["node_files"], ctx["local_files"] = node_files, by_local
         store.put_blob(rid, "node_files", node_files)          # on-demand AI tags its text with these
-        b = tag_board(b, {f.id: f.files for f in findings})
-        ctx["board"] = b
-        store.put_blob(rid, "board", b)
+        boardstore.save(store, rid, bs, {f.id: f.files for f in findings})
+        ctx["boards"] = bs
+        if bs.note:
+            notes.append(bs.note)
         if notes:
             raise Degraded("; ".join(notes))
-        return f"{len(b.nodes)} node(s), {len(b.flows)} flow(s), {len(b.impacts)} annotation(s)"
+        if bs.board is not None:
+            b = bs.board
+            return f"{len(b.nodes)} node(s), {len(b.flows)} flow(s), {len(b.impacts)} annotation(s)"
+        return (f"{len(bs.clusters)} cluster board(s), up to {max(len(b.nodes) for b in bs.clusters.values())} node(s) "
+                f"each, {sum(len(b.flows) for b in bs.clusters.values())} flow(s)")
 
     def llm():
         findings = store.list_findings(rid)
         snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
-        b = ctx.get("board")
+        bs = ctx.get("boards")
+        b = None if bs is None else bs.board or boardstore.merge(list(bs.clusters.values()), bs.overview.about)
         sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                               board=b, concurrency=cfg.llm.concurrency, upfront_flows=cfg.llm.upfront_flows,
                               node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid)
         store.put_findings(rid, findings)
         store.put_blob(rid, "storyboard", sb)
-        if b is not None:
-            store.put_blob(rid, "board", tag_board(b, {f.id: f.files for f in findings}))
+        if bs is not None:                     # the AI pass rewrote flows and the summary on the stored boards' objects
+            boardstore.save(store, rid, bs, {f.id: f.files for f in findings})
         ctx["storyboard"] = sb
         if svc.llm is None:
             raise Degraded("no LLM configured; deterministic storyboard only")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_board.py tests/test_large_change.py -q`
Expected: `37 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `366 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/store.py backend/codetortoise/board.py backend/codetortoise/boardstore.py backend/codetortoise/fixture_large.py backend/codetortoise/pipeline.py backend/tests/test_board.py backend/tests/test_large_change.py
git commit -m "feat(board): an overview and one board per cluster, 30 nodes a board"
```

---

### Task 3: Overview, cluster boards, expansion and locate over HTTP

Spec §4. `GET /api/reviews/{id}/overview` returns the overview (layer names filled in), or 404 "this review is shown
as one board". `GET …/board?cluster=C3` returns a cluster's board; without `cluster` a split review answers 404 "this
review is split into clusters: see its overview"; an unknown cluster is 404 "That cluster no longer exists after the
re-run.". `expand=N12:callers,N9:callees` adds up to `expand_step` (10) callers or callees per asked node, most
affected first, lays the board out again and recounts the badges (400 for a bad expansion); it works on single boards
too. `GET …/locate?node=|flow=|finding=` returns `{cluster}` (null for a single board, 404 for an unknown id). ✦
Explain on a flow and the AI context find the board holding the flow (`boardstore.with_flow`, `combined`).
`codetortoise fixture-demo --large` serves the generated fixture.

**Files:**
- Modify: `backend/codetortoise/board.py`
- Modify: `backend/codetortoise/llm/ondemand.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `backend/codetortoise/cli.py`
- Modify: `backend/tests/test_large_change.py`

**Interfaces:**
- Consumes: `boardstore.*`, `BoardSet`, blobs `overview`, `board:C<n>`, `node_cluster` (Task 2).
- Produces: `board.expand_board(b, im, asks, *, step, ranges, depot_of, layer_name, is_test, home=None) -> Board`;
  HTTP `GET …/overview`, `GET …/board?cluster=&expand=`, `GET …/locate`; CLI `fixture-demo --large`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_large_change.py` (replace the whole file):

```python
"""A large change is split into clusters with an overview (spec 2026-10-03-large-change-boards), end to end."""
import pytest
from helpers import make_services

from codetortoise import boardstore
from codetortoise.fixture_large import build_large_fixture
from codetortoise.pipeline import run_review


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    d = tmp_path_factory.mktemp("large")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    rid = svc.store.create_review("large", "owner", fx.cls)
    run_review(rid, svc)
    return svc, rid


def test_a_large_change_gets_an_overview_and_a_board_per_cluster(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    assert ov is not None and boardstore.board(svc.store, rid) is None              # no single board
    assert {c.name for c in ov.clusters} == {"app/telemetry", "drv/dma", "drv/uart", "hal/regs", "svc/logger",
                                             "svc/stats", "tests"}
    assert [c.id for c in ov.clusters] == [f"C{i}" for i in range(1, len(ov.clusters) + 1)]
    assert ov.clusters[-1].name == "tests"                                          # least risky last
    boards = boardstore.boards(svc.store, rid)
    assert set(boards) == {c.id for c in ov.clusters}
    assert all(len(b.nodes) <= 30 for b in boards.values())
    stage = next(s for s in svc.store.list_stages(rid) if s["name"] == "board")
    assert stage["status"] == "ok" and "7 cluster board(s)" in stage["message"]


def test_every_changed_function_and_flow_is_on_exactly_one_board(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    im = svc.store.get_blob(rid, "impact")
    homes = [n for c in ov.clusters for n in c.nodes]
    assert sorted(homes) == sorted(im["changed"]) and len(homes) == len(set(homes))
    flows = [f.id for b in boardstore.boards(svc.store, rid).values() for f in b.flows]
    assert len(flows) == len(set(flows)) == ov.totals["flows"]
    node_cluster = svc.store.get_blob(rid, "node_cluster")
    assert all(node_cluster[n] == c.id for c in ov.clusters for n in c.nodes)


def test_cluster_boards_mark_visitors_and_link_clusters(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    regs = next(c for c in ov.clusters if c.name == "hal/regs")
    b = boardstore.board(svc.store, rid, regs.id)
    assert b.cluster.id == regs.id and b.cluster.name == "hal/regs"
    visitors = [n for n in b.nodes if n.home]
    assert visitors and all(n.home != regs.id for n in visitors)
    assert {n.label for n in b.nodes if n.change and not n.home} == {"regs_a1", "regs_a2", "regs_a3", "regs_b1",
                                                                     "regs_b2"}
    uart = next(c for c in ov.clusters if c.name == "drv/uart")
    assert any(l.src == uart.id and l.dst == regs.id and l.calls > 0 for l in ov.links)      # uart calls into regs
    assert {f.path.split("/")[-2] for d in b.about.tree for f in d.files} == {"regs"}         # its own files only


def test_nodes_with_neighbours_off_the_board_say_how_many(large):
    svc, rid = large
    boards = boardstore.boards(svc.store, rid)
    assert any(n.more_callers > 0 for b in boards.values() for n in b.nodes)


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    from test_web import InlineRunner, login

    from codetortoise.web.app import create_app, make_authenticator
    d = tmp_path_factory.mktemp("largeapi")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": fx.cls}).json()["id"]
    return svc, owner, rid


def test_the_api_serves_the_overview_and_each_cluster_board(api):
    svc, owner, rid = api
    ov = owner.get(f"/api/reviews/{rid}/overview").json()
    assert ov["totals"]["clusters"] == len(ov["clusters"]) == 7 and ov["links"]
    c1 = ov["clusters"][0]["id"]
    b = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c1}).json()
    assert b["cluster"]["id"] == c1 and len(b["nodes"]) <= 30 and all(n["files"] for n in b["nodes"] if n["path"])
    r = owner.get(f"/api/reviews/{rid}/board")                           # split: there is no single board
    assert r.status_code == 404 and "overview" in r.json()["detail"]
    r = owner.get(f"/api/reviews/{rid}/board", params={"cluster": "C99"})
    assert r.status_code == 404 and r.json()["detail"] == "That cluster no longer exists after the re-run."


def test_the_small_fixture_has_no_overview(fx, tmp_path):
    from test_web import InlineRunner, login

    from codetortoise.web.app import create_app, make_authenticator
    svc = make_services(fx, tmp_path)
    client = login(create_app(svc, InlineRunner(svc), make_authenticator(svc)), "owner")
    rid = client.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    assert client.get(f"/api/reviews/{rid}/board").status_code == 200
    assert client.get(f"/api/reviews/{rid}/overview").status_code == 404
    assert client.get(f"/api/reviews/{rid}/locate", params={"node": "N1"}).json() == {"cluster": None}


def test_expanding_adds_callers_past_the_budget_and_counts_what_is_left(api):
    svc, owner, rid = api
    ov = owner.get(f"/api/reviews/{rid}/overview").json()
    boards = {c["id"]: owner.get(f"/api/reviews/{rid}/board", params={"cluster": c["id"]}).json() for c in ov["clusters"]}
    cid, node = next((cid, n) for cid, b in boards.items() for n in b["nodes"] if n["more_callers"] > 0)
    before = boards[cid]
    after = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": f"{node['id']}:callers"}).json()
    added = len(after["nodes"]) - len(before["nodes"])
    assert added == min(node["more_callers"], svc.cfg.analysis.expand_step) and added > 0
    grown = next(n for n in after["nodes"] if n["id"] == node["id"])
    assert grown["more_callers"] == node["more_callers"] - added
    new = [n for n in after["nodes"] if n["id"] not in {m["id"] for m in before["nodes"]}]
    assert all(any(e["src"] == n["id"] and e["dst"] == node["id"] for e in after["edges"]) for n in new)
    bad = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": "N1:sideways"})
    assert bad.status_code == 400


def test_locate_finds_the_cluster_of_a_node_a_flow_and_a_finding(api):
    svc, owner, rid = api
    ov = owner.get(f"/api/reviews/{rid}/overview").json()
    c = ov["clusters"][1]
    loc = lambda **q: owner.get(f"/api/reviews/{rid}/locate", params=q)          # noqa: E731
    assert loc(node=c["nodes"][0]).json() == {"cluster": c["id"]}
    assert loc(finding=c["finding_ids"][0]).json() == {"cluster": c["id"]}
    flow = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c["id"]}).json()["flows"][0]["id"]
    assert loc(flow=flow).json() == {"cluster": c["id"]}
    assert loc(node="N99999").status_code == 404


def test_explaining_a_flow_updates_the_cluster_board_that_holds_it(tmp_path_factory):
    import json

    import httpx
    from test_web import InlineRunner, login

    from codetortoise.llm.client import LlmClient
    from codetortoise.web.app import create_app, make_authenticator

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": []})
        user = json.loads(req.content)["messages"][1]["content"]
        out = ({"what": "regs_a1 now returns -2 and its caller drops it.", "cites": [f"N{i}" for i in range(1, 400)]}
               if "Describe this call flow" in user else {"summary": "s", "risk": "high", "cites": []})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}]})
    d = tmp_path_factory.mktemp("largeai")
    fx = build_large_fixture(d)
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    svc = make_services(fx, d / "data", llm=llm)
    svc.cfg.llm.upfront_flows = 0
    svc.build_index()
    owner = login(create_app(svc, InlineRunner(svc), make_authenticator(svc)), "owner")
    rid = owner.post("/api/reviews", json={"cls": fx.cls}).json()["id"]
    c3 = owner.get(f"/api/reviews/{rid}/overview").json()["clusters"][2]["id"]
    fl = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c3}).json()["flows"][0]
    assert fl["what_source"] == "template"
    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "flow", "target": fl["id"]}).status_code == 202
    after = next(f for f in owner.get(f"/api/reviews/{rid}/board", params={"cluster": c3}).json()["flows"]
                 if f["id"] == fl["id"])
    assert after["what_source"] == "llm" and after["what"].startswith("regs_a1 now returns -2")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_large_change.py -q`
Expected: FAIL — `5 failed, 4 passed` (`GET …/overview` and `…/locate` answer `404 Not Found`: `KeyError: 'totals'`, `KeyError: 'clusters'`)

- [ ] **Step 3: Implement**

`backend/codetortoise/board.py`:

```diff
diff --git a/backend/codetortoise/board.py b/backend/codetortoise/board.py
index b7c5934..f9cb33a 100644
--- a/backend/codetortoise/board.py
+++ b/backend/codetortoise/board.py
@@ -215,6 +215,7 @@ class ClusterInfo(BaseModel):
     changed: int = 0                                  # changed functions
     flows: int = 0
     findings: int = 0
+    finding_ids: list[str] = Field(default_factory=list)
     nodes: list[str] = Field(default_factory=list)    # its changed nodes
 
 
@@ -788,7 +789,7 @@ def _overview(x: _Ctx, res, about: About, depots: dict[str, str], flows: list[Fl
             id=cl.id, name=cl.name, level=cl.level, also=cl.also, risk=cl.risk, test=cl.test,
             files=sorted({depots[x.local(m)] for m in cl.members if x.local(m) in depots}),
             changed=sum(1 for m in cl.members if x.im.nodes[m].kind == "function"), flows=len(cl.flows),
-            findings=len(cl.findings), nodes=list(cl.members)))
+            findings=len(cl.findings), finding_ids=list(cl.findings), nodes=list(cl.members)))
     owner = {m: cl.id for cl in res.clusters for m in cl.members}
     calls: dict[tuple[str, str], int] = defaultdict(int)
     for e in x.im.edges:
@@ -816,6 +817,50 @@ def _overview(x: _Ctx, res, about: About, depots: dict[str, str], flows: list[Fl
                     merged_over_limit=res.merged_over_limit)
 
 
+def expand_board(b: Board, im: ImpactModel, asks: list[tuple[str, str]], *, step: int,
+                 ranges: dict[str, list[int]], depot_of: dict[str, Files], layer_name: Callable[[int], str],
+                 is_test: Callable[[str], bool], home: dict[str, str] | None = None) -> Board:
+    """`b` with up to `step` more callers or callees of each asked node ("+N callers"), most affected first, laid out
+    again. Asks are applied in order, so a node added by one can be expanded by the next. The board may pass its
+    node budget: the reader asked for it."""
+    out = b.model_copy(deep=True)
+    on = {n.id for n in out.nodes}
+    score = {x.node: x.score for x in im.blast}
+    callers: dict[str, set[str]] = defaultdict(set)
+    callees: dict[str, set[str]] = defaultdict(set)
+    for e in im.edges:
+        if e.kind in ("call", "virtual"):
+            callers[e.dst].add(e.src)
+            callees[e.src].add(e.dst)
+    for nid, way in asks:
+        if nid not in on:
+            continue
+        cands = [n for n in (callers if way == "callers" else callees)[nid] - on if n in im.nodes and not is_test(n)]
+        for n in sorted(cands, key=lambda n: (-score.get(n, 0.0), int(n[1:]) if n[1:].isdigit() else 0))[:step]:
+            node = im.nodes[n]
+            h = (home or {}).get(n)
+            files = depot_of.get(n) or []
+            out.nodes.append(BoardNode(id=n, key=node.key, label=node.label, kind=node.kind,
+                                       layer=node.layer if node.layer is not None else -1,
+                                       path=files[0] if node.file and files else None, local=node.file,
+                                       range=ranges.get(node.key), home=h if out.cluster and h and h != out.cluster.id
+                                       else None))
+            on.add(n)
+    out.edges = [BoardEdge(src=e.src, dst=e.dst, kind=e.kind, status=e.status, confidence=e.confidence)
+                 for e in im.edges if e.src in on and e.dst in on]
+    xs = barycentre_layout({n.id: n.layer if n.layer is not None else -1 for n in out.nodes},
+                           [(e.src, e.dst) for e in out.edges])
+    for n in out.nodes:
+        n.x = xs.get(n.id, n.x)
+        n.more_callers = len({s_ for s_ in callers.get(n.id, ()) if s_ not in on and not is_test(s_)})
+        n.more_callees = len({d for d in callees.get(n.id, ()) if d not in on and not is_test(d)})
+    have = {lv.level for lv in out.layers}
+    for lv in sorted({n.layer for n in out.nodes if n.layer is not None} - have):
+        out.layers.append(BoardLayer(level=lv, name=layer_name(lv) if lv >= 0 else "other"))
+    out.layers.sort(key=lambda lv: -lv.level)
+    return out
+
+
 def _tree_prefix(depots: list[str]) -> str:
     """Prefix stripped from the change tree: everything above the deepest directory the files share, so that
     directory itself stays visible (a change inside one directory shows that directory, not ".")."""
```

`backend/codetortoise/llm/ondemand.py`:

```diff
diff --git a/backend/codetortoise/llm/ondemand.py b/backend/codetortoise/llm/ondemand.py
index 6b8fd7f..3541362 100644
--- a/backend/codetortoise/llm/ondemand.py
+++ b/backend/codetortoise/llm/ondemand.py
@@ -13,6 +13,7 @@ from datetime import UTC, datetime
 
 from pydantic import BaseModel, Field
 
+from codetortoise import boardstore
 from codetortoise.board import Board
 from codetortoise.detectors.base import Finding
 from codetortoise.facts.model import Facts
@@ -63,7 +64,7 @@ def context_for(svc: Services, rid: int) -> tuple[AiContext, Board, list[Finding
     cs = ChangeSet.model_validate(store.get_blob(rid, "changeset") or {"cls": [], "files": []})
     after = [Facts.model_validate(f) for f in store.get_blob(rid, "facts_after") or []]
     findings = store.list_findings(rid)
-    board = Board.model_validate(store.get_blob(rid, "board") or {"about": {"intent": ""}})
+    board = boardstore.combined(store, rid) or Board(about={"intent": ""})    # a split review: all its boards
     snippets = collect_snippets(impact, cs, after) if impact.nodes else {}
     ctx = AiContext(impact, findings, snippets, svc.cfg.llm.max_context_tokens, store.get_blob(rid, "node_files"))
     return ctx, board, findings, cs
@@ -113,13 +114,13 @@ def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
             raise Unchecked(UNCHECKED)
         with _lock(rid):
             _same(svc, rid, seen)
-            board = Board.model_validate(svc.store.get_blob(rid, "board") or {"about": {"intent": ""}})
-            now = next((f for f in board.flows if f.id == target and f.path == fl.path), None)
+            held = boardstore.with_flow(svc.store, rid, target)          # the board holding the flow, as it is now
+            now = next((f for f in held[1].flows if f.id == target and f.path == fl.path), None) if held else None
             if now is None:
                 raise Changed(CHANGED)
             now.what, now.what_source, now.what_files, now.title = trial.what, "llm", trial.what_files, trial.title
             findings = svc.store.list_findings(rid)
-            svc.store.put_blob(rid, "board", tag_board(board, {f.id: f.files for f in findings}))
+            boardstore.put(svc.store, rid, held[0], tag_board(held[1], {f.id: f.files for f in findings}))
     elif kind == "finding":
         f = next((f for f in findings if f.id == target), None)
         if f is None:
@@ -163,8 +164,7 @@ def _same(svc: Services, rid: int, seen: str) -> None:
 def check_target(svc: Services, rid: int, kind: str, target: str) -> None:
     """Fail fast (NotFound) before queueing an explanation of something that doesn't exist."""
     if kind == "flow":
-        board = svc.store.get_blob(rid, "board") or {}
-        if not any(f.get("id") == target for f in board.get("flows", [])):
+        if boardstore.with_flow(svc.store, rid, target) is None:
             raise NotFound(f"flow {target} not found")
     elif kind == "finding":
         if not any(f.id == target for f in svc.store.list_findings(rid)):
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index a38b248..a8dfd1f 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -10,9 +10,13 @@ from fastapi import Depends, FastAPI, HTTPException, Request, Response
 from fastapi.responses import FileResponse, StreamingResponse
 from pydantic import BaseModel, Field
 
-from codetortoise.board import Board
+from codetortoise import boardstore
+from codetortoise.board import Board, expand_board, is_test_path
+from codetortoise.facts.model import Facts
 from codetortoise.health import run_health
+from codetortoise.impact import ImpactModel
 from codetortoise.llm import ondemand, tortoise
+from codetortoise.paths import canon
 from codetortoise.pipeline import JobRunner
 from codetortoise.provenance import tag_board
 from codetortoise.services import Services
@@ -183,19 +187,94 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
 
         return StreamingResponse(gen(), media_type="text/event-stream")
 
+    def named(layers: list[dict]) -> None:
+        overrides = store.kv_get("layer_overrides") or {}
+        for layer in layers:
+            if str(layer["level"]) in overrides:
+                layer["name"] = overrides[str(layer["level"])]
+
+    @app.get("/api/reviews/{rid}/overview")
+    def overview(rid: int, _: str = Depends(user_of)):
+        """A split review's overview (spec 2026-10-03-large-change-boards §4); 404 for a review shown as one board."""
+        review_or_404(rid)
+        ov = boardstore.overview(store, rid)
+        if ov is None:
+            raise HTTPException(404, "this review is shown as one board")
+        out = ov.model_dump()
+        named(out["layers"])
+        return out
+
     @app.get("/api/reviews/{rid}/board")
-    def board(rid: int, _: str = Depends(user_of)):
+    def board(rid: int, cluster: str | None = None, expand: str | None = None, _: str = Depends(user_of)):
         review_or_404(rid)
-        b = store.get_blob(rid, "board")
+        b = boardstore.board(store, rid, cluster)
         if b is None:
+            if cluster:
+                raise HTTPException(404, "That cluster no longer exists after the re-run.")
+            if boardstore.overview(store, rid) is not None:
+                raise HTTPException(404, "this review is split into clusters: see its overview")
             raise HTTPException(404, "board not built yet")
         # boards stored by an older version get current defaults and file tags (spec §14.3)
-        b = tag_board(Board.model_validate(b), {f.id: f.files for f in store.list_findings(rid)}).model_dump()
-        overrides = store.kv_get("layer_overrides") or {}
-        for layer in b.get("layers", []):
-            if str(layer["level"]) in overrides:
-                layer["name"] = overrides[str(layer["level"])]
-        return b
+        tags = {f.id: f.files for f in store.list_findings(rid)}
+        b = tag_board(b, tags)
+        if expand:
+            b = tag_board(expanded(rid, b, expand), tags)
+        out = b.model_dump()
+        named(out.get("layers", []))
+        return out
+
+    def expanded(rid: int, b: Board, expand: str) -> Board:
+        """`expand` is "N12:callers,N9:callees": up to `analysis.expand_step` neighbours each, in order."""
+        asks = []
+        for part in expand.split(",")[:20]:
+            nid, _, way = part.strip().partition(":")
+            if way not in ("callers", "callees") or not nid:
+                raise HTTPException(400, f"bad expansion {part!r}: use <node>:callers or <node>:callees")
+            asks.append((nid, way))
+        im = ImpactModel.model_validate(store.get_blob(rid, "impact") or {})
+        ranges: dict[str, list[int]] = {}
+        for fx in store.get_blob(rid, "facts_after") or []:
+            facts = Facts.model_validate(fx)
+            ranges.update({f.usr: [f.start_line, f.end_line] for f in facts.functions})
+            ranges.update({f"field:{a.field}": [a.decl_line, a.decl_line] for a in facts.fields if a.decl_line})
+        lm = svc.layers.get()
+        root = canon(str(cfg.workspace.root)).rstrip("/") + "/"
+
+        def layer_name(lv: int) -> str:
+            layer = lm.layer(lv) if lm else None
+            return layer.name.split(": ", 1)[-1] if layer else f"L{lv}"
+
+        def is_test(nid: str) -> bool:
+            f = im.nodes[nid].file or ""
+            return bool(f) and is_test_path(f[len(root):] if f.startswith(root) else f)
+        return expand_board(b, im, asks, step=cfg.analysis.expand_step, ranges=ranges,
+                            depot_of=store.get_blob(rid, "node_files") or {}, layer_name=layer_name, is_test=is_test,
+                            home=store.get_blob(rid, "node_cluster") or {})
+
+    @app.get("/api/reviews/{rid}/locate")
+    def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
+               _: str = Depends(user_of)):
+        """The cluster to open for a node, flow or finding; null for a review shown as one board."""
+        review_or_404(rid)
+        ov = boardstore.overview(store, rid)
+        if ov is None:
+            return {"cluster": None}
+        if flow:
+            held = boardstore.with_flow(store, rid, flow)
+            if held:
+                return {"cluster": held[0]}
+        elif finding:
+            c = next((c for c in ov.clusters if finding in c.finding_ids), None)
+            if c:
+                return {"cluster": c.id}
+        elif node:
+            home = (store.get_blob(rid, "node_cluster") or {}).get(node)
+            if home:
+                return {"cluster": home}
+            for cid, b in boardstore.boards(store, rid).items():
+                if any(n.id == node for n in b.nodes):
+                    return {"cluster": cid}
+        raise HTTPException(404, "not on any board of this review")
 
     @app.get("/api/reviews/{rid}/source")
     def source(rid: int, path: str, side: Literal["before", "after"] = "after", _: str = Depends(user_of)):
```

`backend/codetortoise/cli.py`:

```diff
diff --git a/backend/codetortoise/cli.py b/backend/codetortoise/cli.py
index 1d5ca3d..238b246 100644
--- a/backend/codetortoise/cli.py
+++ b/backend/codetortoise/cli.py
@@ -155,8 +155,9 @@ def cmd_fetch_libclang(args) -> int:
 
 def cmd_fixture_demo(args) -> int:
     from codetortoise.fixture import build_fixture
+    from codetortoise.fixture_large import build_large_fixture
     dest = Path(args.dir).resolve()
-    fx = build_fixture(dest)
+    fx = build_large_fixture(dest) if args.large else build_fixture(dest)
     cfg = {
         "owner": "demo",
         "server": {"host": "127.0.0.1", "port": args.port, "public_url": f"http://127.0.0.1:{args.port}",
@@ -212,6 +213,7 @@ def main(argv: list[str] | None = None) -> int:
     s.add_argument("--port", type=int, default=8765)
     s.add_argument("--llm-base-url")
     s.add_argument("--llm-model", default="gpt-4o-mini")
+    s.add_argument("--large", action="store_true", help="a generated project whose CLs 201+202 need several boards")
     s.set_defaults(fn=cmd_fixture_demo)
     args = p.parse_args(argv)
     try:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_large_change.py -q`
Expected: `9 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `371 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/board.py backend/codetortoise/llm/ondemand.py backend/codetortoise/web/app.py backend/codetortoise/cli.py backend/tests/test_large_change.py
git commit -m "feat(api): overview, cluster boards, expansion and locate; explanations find their cluster board"
```

---

### Task 4: The overview page, cluster boards, findings by cluster, phone

Spec §5. `/r/:id` shows the overview for a split review (else today's board; with `?node=` it asks `locate` and opens
the right cluster); `/r/:id/c/:cid` shows a cluster's board. The **overview**: totals in the header, layer bands with
a block per cluster (name, risk, counts, up to three links in words, "also in …"); a click selects a block and
outlines the clusters it links to, **Open ›**, a double click or Enter opens it; the change panel covers the whole
change and a file opens its cluster's board with the file in the viewer. A **cluster board**: breadcrumb "Overview ›
name", ‹ › ("Previous cluster", "Next cluster") and "C2 of 7"; visitors dashed with "· home ›" to their board,
focused on the node; "+N callers / +N callees" badges add neighbours (`?x=` in the address, remembered per cluster)
and "N nodes · Reset" removes them; prefs are kept per cluster (`<id>.<cluster>`); the panel's "Whole change ›" goes
back. The board's toolbar now sits above open cards (cards could cover Reset). **Findings** are grouped by cluster
with a "Findings of" filter. On the **phone** the overview stacks full-width blocks and the ☰ menu lists Overview and
the clusters. The e2e tests run a third CodeTortoise on the generated fixture (`e2e/serve-large.sh`, port 8796).

**Files:**
- Modify: `frontend/src/board/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/board/prefs.ts`
- Create: `frontend/src/board/overview.ts`
- Modify: `frontend/src/board/Canvas.tsx`
- Modify: `frontend/src/board/Board.tsx`
- Modify: `frontend/src/board/ChangePanel.tsx`
- Modify: `frontend/src/board/phone/PhoneBoard.tsx`
- Create: `frontend/src/board/OverviewPage.tsx`
- Create: `frontend/src/board/ClusterBoard.tsx`
- Modify: `frontend/src/pages/Review.tsx`
- Modify: `frontend/src/components/Findings.tsx`
- Modify: `frontend/src/board/board.css`
- Test: `frontend/src/board/overview.test.ts`
- Test: `frontend/e2e/serve-large.sh`
- Modify: `frontend/playwright.config.ts`
- Test: `frontend/e2e/large.spec.ts`

**Interfaces:**
- Consumes: HTTP `…/overview`, `…/board?cluster=&expand=`, `…/locate` (Task 3).
- Produces: `types.ts` `BoardNode.home`, `.more_callers`, `.more_callees`, `Board.cluster`, `ClusterInfo`,
  `ClusterLink`, `Overview`; `api.board(id, cluster?, expand?)`, `api.overview(id)`, `api.locate(id, q)`;
  `prefs.BoardKey`, `keys.expand`, `loadExpand(key)`; `board/overview.ts` `bandsOf`, `linkLines(ov, id, max)`,
  `linkedTo`, `stepCluster`, `clusterOfFile`; components `OverviewPage`, `ClusterBoard`; `Board` props `cluster`,
  `expansion`, `openPath`, `BUDGET = 30`; `Canvas` props `onExpand`, `onHome`, `homeName`; `Findings` prop `groups`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/board/overview.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { bandsOf, clusterOfFile, linkLines, linkedTo, stepCluster } from "./overview";
import type { Overview } from "./types";

const c = (id: string, name: string, level: number | null, over: Partial<Overview["clusters"][0]> = {}) => ({
  id, name, level, also: [], risk: null, test: false, files: [], changed: 1, flows: 0, findings: 0, finding_ids: [], nodes: [], ...over,
});
const ov: Overview = {
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] },
  clusters: [c("C1", "svc/logger", 2, { files: ["//d/svc/logger.c"] }), c("C2", "drv/uart", 1, { also: [0] }),
             c("C3", "app/telemetry", 3), c("C4", "tests", null, { test: true })],
  links: [{ src: "C2", dst: "C1", calls: 22, fields: 3 }, { src: "C1", dst: "C3", calls: 9, fields: 0 },
          { src: "C4", dst: "C2", calls: 1, fields: 0 }],
  layers: [{ level: 3, name: "app" }, { level: 2, name: "service" }, { level: 1, name: "driver" }, { level: 0, name: "hal" },
           { level: -1, name: "other" }],
  totals: { files: 9, clusters: 4, flows: 20, findings: 5, changed: 12 }, merged_over_limit: 0,
};

describe("bandsOf", () => {
  it("puts each cluster in its layer, top layer first, unlayered last, and drops empty layers", () => {
    expect(bandsOf(ov).map((b) => [b.name, b.clusters.map((x) => x.id)])).toEqual(
      [["app", ["C3"]], ["service", ["C1"]], ["driver", ["C2"]], ["other", ["C4"]]]);
  });
});

describe("linkLines", () => {
  it("says what a cluster calls and what calls it, in words", () => {
    expect(linkLines(ov, "C1")).toEqual(["← drv/uart: 22 calls, 3 shared fields", "→ app/telemetry: 9 calls"]);
    expect(linkLines(ov, "C3")).toEqual(["← svc/logger: 9 calls"]);
  });
  it("keeps it short on a phone", () => {
    expect(linkLines(ov, "C2", 1)).toEqual(["→ svc/logger: 22 calls, 3 shared fields"]);
  });
});

describe("linkedTo", () => {
  it("is every cluster linked either way", () => {
    expect([...linkedTo(ov, "C2")].sort()).toEqual(["C1", "C4"]);
  });
});

describe("stepCluster", () => {
  it("moves through the clusters in risk order, wrapping", () => {
    expect(stepCluster(ov, "C1", 1)).toBe("C2");
    expect(stepCluster(ov, "C4", 1)).toBe("C1");
    expect(stepCluster(ov, "C1", -1)).toBe("C4");
  });
});

describe("clusterOfFile", () => {
  it("finds the cluster whose changed code is in a file", () => {
    expect(clusterOfFile(ov, "//d/svc/logger.c")).toBe("C1");
    expect(clusterOfFile(ov, "//d/none.c")).toBeNull();
  });
});
```

`frontend/e2e/serve-large.sh`:

```
#!/usr/bin/env bash
# Starts a CodeTortoise on the generated large fixture (CLs 201+202 need an overview and cluster boards).
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --large --dir "$DIR" --port 8796 >/dev/null
exec $CMD serve --config "$DIR/tortoise.yaml"
```

`frontend/playwright.config.ts`:

```diff
diff --git a/frontend/playwright.config.ts b/frontend/playwright.config.ts
index e8ca49e..d3dbed8 100644
--- a/frontend/playwright.config.ts
+++ b/frontend/playwright.config.ts
@@ -9,5 +9,7 @@ export default defineConfig({
     // AI tests (e2e/ai.spec.ts, e2e/mention.spec.ts): a fake OpenAI-compatible model and a CodeTortoise that uses it
     { command: "python3 e2e/fake_llm.py 8797", url: "http://127.0.0.1:8797/v1/models", timeout: 30_000, reuseExistingServer: false },
     { command: "bash e2e/serve-ai.sh", url: "http://127.0.0.1:8798/api/me", timeout: 120_000, reuseExistingServer: false },
+    // large changes (e2e/large.spec.ts): the generated fixture whose CLs need several boards
+    { command: "bash e2e/serve-large.sh", url: "http://127.0.0.1:8796/api/me", timeout: 120_000, reuseExistingServer: false },
   ],
 });
```

`frontend/e2e/large.spec.ts`:

```ts
import { expect, type Locator, type Page, test } from "@playwright/test";
import { login } from "./helpers";

const LARGE = "http://127.0.0.1:8796";      // e2e/serve-large.sh: the generated fixture, CLs 201+202

/** Review the large fixture's CLs and wait for the overview. */
async function startLarge(page: Page) {
  await login(page);
  await page.getByLabel("Changelists (shelved or submitted)").fill("201 202");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator(".ov-block").first()).toBeVisible({ timeout: 60_000 });
}

/** Press and release on a badge or link inside a node. In Whole graph, open cards and the toolbar can sit over small
 * badges and the lens keeps nodes moving, so a pointer click waits forever; the canvas acts on pointerdown/up. */
async function tap(target: Locator) {
  await target.dispatchEvent("pointerdown", { bubbles: true, pointerId: 1, button: 0 });
  await target.dispatchEvent("pointerup", { bubbles: true, pointerId: 1, button: 0 });
}

const block = (page: Page, name: string) => page.locator(".ov-block", { has: page.locator(".nm", { hasText: new RegExp(`^${name}`) }) });

test.describe("a large change", () => {
  test.use({ baseURL: LARGE, viewport: { width: 1440, height: 900 } });

  test("the overview shows each cluster in its layer, with risk, counts and links", async ({ page }) => {
    await startLarge(page);
    await expect(page.locator(".ov-block")).toHaveCount(7);
    await expect(page.getByText("13 files · 7 clusters")).toBeVisible();
    const uart = block(page, "drv/uart");
    await expect(uart.locator(".ct")).toContainText("5 changed");
    await expect(uart.locator(".ln").first()).toContainText(/calls/);
    await expect(page.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
    await uart.click();                                                   // select: linked clusters are outlined
    await expect(uart).toHaveClass(/sel/);
    await expect(block(page, "hal/regs")).toHaveClass(/lit/);
    await expect(block(page, "app/telemetry")).not.toHaveClass(/lit/);
  });

  test("a cluster's board: breadcrumb, ‹ › and back to the overview", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await expect(page).toHaveURL(/\/c\/C\d+$/);
    await expect(page.locator(".bd-crumb")).toContainText("Overview › hal/regs");
    expect(await page.locator(".bd-node").count()).toBeLessThanOrEqual(30);
    const here = page.url();
    await page.getByRole("button", { name: "Next cluster" }).click();
    await expect(page).not.toHaveURL(here);
    await page.getByRole("button", { name: "Previous cluster" }).click();
    await expect(page).toHaveURL(here);
    await page.locator(".bd-crumb").getByRole("link", { name: "Overview" }).click();
    await expect(page.locator(".ov-block")).toHaveCount(7);
  });

  test("a visitor opens its own cluster's board, focused on it", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await page.getByRole("button", { name: "Whole graph" }).click();
    await expect(page.locator(".bd-node.visitor").first()).toBeVisible();
    const visitor = page.locator(".bd-node.visitor").first();
    const label = (await visitor.locator(".lbl").textContent())!;
    await tap(visitor.locator(".bd-home"));
    await expect(page).toHaveURL(/\/c\/C\d+\?node=N\d+/);
    await expect(page.locator(".bd-crumb")).not.toContainText("hal/regs");
    await expect(page.locator(".bd-card .hd b", { hasText: new RegExp(`^${label}$`) })).toBeVisible();
  });

  test("+N callers adds them past the budget, and Reset takes them away", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await page.getByRole("button", { name: "Whole graph" }).click();
    const before = await page.locator(".bd-node").count();
    await expect(page.locator(".bd-more-nb [data-act='callers']").first()).toBeVisible();
    const more = page.locator(".bd-more-nb [data-act='callers']").first();
    const n = Number((await more.textContent())!.match(/\d+/)![0]);
    await tap(more);
    await expect(page.locator(".bd-node")).toHaveCount(before + Math.min(n, 10));
    await expect(page).toHaveURL(/x=N\d+(%3A|:)callers/);
    const reset = page.getByRole("button", { name: /nodes · Reset/ });
    await expect(reset).toHaveText(`${before + Math.min(n, 10)} nodes · Reset`);
    await reset.click();
    await expect(page.locator(".bd-node")).toHaveCount(before);
    await expect(reset).toHaveCount(0);
  });

  test("a citation opens the cluster that holds the node", async ({ page }) => {
    await startLarge(page);
    const rid = page.url().match(/\/r\/(\d+)/)![1];
    const ov = await (await page.request.get(`/api/reviews/${rid}/overview`)).json();
    const regs = ov.clusters.find((c: { name: string }) => c.name === "hal/regs");
    await page.goto(`/r/${rid}?node=${regs.nodes[0]}`);
    await expect(page).toHaveURL(new RegExp(`/c/${regs.id}\\?node=${regs.nodes[0]}`));
    await expect(page.locator(".bd-crumb")).toContainText("hal/regs");
  });

  test("findings are grouped by cluster", async ({ page }) => {
    await startLarge(page);
    await page.getByRole("link", { name: /Findings/ }).click();
    await expect(page.getByRole("region", { name: "Findings in hal/regs" })).toBeVisible();
    const of = page.getByLabel("Findings of");
    await of.selectOption({ label: (await of.locator("option", { hasText: "hal/regs" }).textContent())! });
    await expect(page.locator(".fg")).toHaveCount(1);
  });
});

test.describe("a large change on a phone", () => {
  test.use({ baseURL: LARGE, viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the overview stacks the clusters; opening one shows its phone board", async ({ page }) => {
    await startLarge(page);
    const first = page.locator(".ov-block").first(), second = page.locator(".ov-block").nth(1);
    const a = (await first.boundingBox())!, b = (await second.boundingBox())!;
    expect(b.y).toBeGreaterThan(a.y + a.height - 1);                      // stacked, not side by side
    expect(a.width).toBeGreaterThan(300);
    await first.getByRole("button", { name: /^Open/ }).click();
    await expect(page.locator(".ph-tabs")).toBeVisible();
    await page.getByRole("button", { name: "Review menu" }).click();
    await expect(page.locator(".ph-menu").getByRole("link", { name: "Overview" })).toBeVisible();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/board/overview.test.ts && npx tsc --noEmit && npm run build && npx playwright test e2e/large.spec.ts`
Expected: FAIL — `Error: Cannot find module './overview'` (`Test Files  1 failed (1)`; the command stops there)

- [ ] **Step 3: Implement**

`frontend/src/board/types.ts`:

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index 16c85c4..52d219c 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -3,6 +3,10 @@ export interface NodeChange { kind: "modified" | "signature" | "added" | "remove
 export interface BoardNode {
   id: string; key: string; label: string; kind: "function" | "field"; layer: number | null;
   path: string | null; local: string | null; range: [number, number] | null; change: NodeChange | null; x: number; warn: number;
+  /** A visitor: the cluster this node belongs to (spec 2026-10-03-large-change-boards §3). */
+  home?: string | null;
+  /** Callers / callees not on the board, for "+N callers" (absent on boards stored before clusters). */
+  more_callers?: number; more_callees?: number;
 }
 export interface BoardEdge {
   src: string; dst: string; kind: "call" | "virtual" | "writes" | "reads"; status: string; confidence: string;
@@ -28,5 +32,18 @@ export interface About {
 export interface Board {
   nodes: BoardNode[]; edges: BoardEdge[]; flows: BoardFlow[]; impacts: Annotation[];
   layers: { level: number; name: string }[]; about: About; hidden_nodes: number;
+  /** A cluster's board in a split review. */
+  cluster?: { id: string; name: string } | null;
+}
+/** A split review's overview, as served by GET /api/reviews/{id}/overview. */
+export interface ClusterInfo {
+  id: string; name: string; level: number | null; also: number[]; risk: string | null; test: boolean; files: string[];
+  changed: number; flows: number; findings: number; finding_ids: string[]; nodes: string[];
+}
+export interface ClusterLink { src: string; dst: string; calls: number; fields: number }
+export interface Overview {
+  about: About; clusters: ClusterInfo[]; links: ClusterLink[]; layers: { level: number; name: string }[];
+  totals: { files: number; clusters: number; flows: number; findings: number; changed: number };
+  merged_over_limit: number;
 }
 export interface SourceText { path: string; depot: string; rev: string; text: string; changed: boolean }
```

`frontend/src/api.ts`:

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index 889a169..4f11fa8 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -42,8 +42,8 @@ export interface Health { checks: HealthCheck[]; ready: boolean; index_generatio
   p4_sources: Record<string, string>;
   ai: { limits?: { per_review: number; per_person_daily: number; per_mention: number }; calls_today?: number } }
 
-export type { Board, SourceText } from "./board/types";
-import type { Board, SourceText } from "./board/types";
+export type { Board, Overview, SourceText } from "./board/types";
+import type { Board, Overview, SourceText } from "./board/types";
 
 export class ApiError extends Error {
   constructor(public status: number, message: string) { super(message); }
@@ -74,7 +74,15 @@ export const api = {
   createReview: (cls: number[], title?: string) => call<ReviewRow>("POST", "/api/reviews", { cls, title }),
   review: (id: number) => call<ReviewDetail>("GET", `/api/reviews/${id}`),
   rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
-  board: (id: number) => call<Board>("GET", `/api/reviews/${id}/board`),
+  board: (id: number, cluster?: string | null, expand?: string[]) => {
+    const q = new URLSearchParams();
+    if (cluster) q.set("cluster", cluster);
+    if (expand?.length) q.set("expand", expand.join(","));
+    return call<Board>("GET", `/api/reviews/${id}/board${q.size ? `?${q}` : ""}`);
+  },
+  overview: (id: number) => call<Overview>("GET", `/api/reviews/${id}/overview`),
+  locate: (id: number, q: { node?: string; flow?: string; finding?: string }) =>
+    call<{ cluster: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
     call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
   findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`),
```

`frontend/src/board/prefs.ts`:

```diff
diff --git a/frontend/src/board/prefs.ts b/frontend/src/board/prefs.ts
index 3541511..ee20dd5 100644
--- a/frontend/src/board/prefs.ts
+++ b/frontend/src/board/prefs.ts
@@ -16,13 +16,17 @@ export function save(key: string, value: unknown): void {
   }
 }
 
+/** Whose saved state: a review's board, or one cluster's board in a split review ("12.C3"). */
+export type BoardKey = number | string;
+
 export const keys = {
-  moved: (reviewId: number) => `ct.board.${reviewId}.moved`,
-  layout: (reviewId: number) => `ct.board.${reviewId}.layout`,
+  moved: (reviewId: BoardKey) => `ct.board.${reviewId}.moved`,
+  layout: (reviewId: BoardKey) => `ct.board.${reviewId}.layout`,
   about: "ct.panel.about",
   flowH: "ct.panel.flowH",
-  tab: (reviewId: number) => `ct.board.${reviewId}.tab`,
-  panelTab: (reviewId: number) => `ct.board.${reviewId}.panelTab`,
+  tab: (reviewId: BoardKey) => `ct.board.${reviewId}.tab`,
+  panelTab: (reviewId: BoardKey) => `ct.board.${reviewId}.panelTab`,
+  expand: (reviewId: BoardKey) => `ct.board.${reviewId}.expand`,
   viewerView: "ct.viewer.view",
   viewerW: "ct.panel.viewerW",
   aboutW: "ct.panel.aboutW",
@@ -36,7 +40,7 @@ export function loadLens(): 0 | 2 | 4 {
   return v === 0 || v === 2 || v === 4 ? v : 2;
 }
 
-export function loadLayout(reviewId: number): "layers" | "depth" | null {
+export function loadLayout(reviewId: BoardKey): "layers" | "depth" | null {
   const v = load<unknown>(keys.layout(reviewId), null);
   return v === "layers" || v === "depth" ? v : null;
 }
@@ -46,7 +50,7 @@ const finite = (x: unknown) => typeof x === "number" && Number.isFinite(x);
 const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
 
 /** 2-D moves per layout; also reads the first board's x-only `{id: x}` shape (those were layer-band moves). */
-export function loadMovedAll(reviewId: number): { layers: Moved; depth: Moved } {
+export function loadMovedAll(reviewId: BoardKey): { layers: Moved; depth: Moved } {
   const empty = { layers: {}, depth: {} };
   const v = load<unknown>(keys.moved(reviewId), empty);
   if (!isObj(v)) return empty;
@@ -78,13 +82,13 @@ export function loadSize(key: string, min: number, max: number): number | null {
 }
 
 export type PhoneTab = "flows" | "map" | "files" | "summary";
-export function loadTab(reviewId: number): PhoneTab | null {
+export function loadTab(reviewId: BoardKey): PhoneTab | null {
   const v = load<unknown>(keys.tab(reviewId), null);
   return v === "flows" || v === "map" || v === "files" || v === "summary" ? v : null;
 }
 
 export type PanelTab = "summary" | "cls";
-export function loadPanelTab(reviewId: number): PanelTab {
+export function loadPanelTab(reviewId: BoardKey): PanelTab {
   return load<unknown>(keys.panelTab(reviewId), null) === "cls" ? "cls" : "summary";
 }
 
@@ -92,3 +96,9 @@ export type ViewerView = "changes" | "full";
 export function loadViewerView(): ViewerView {
   return load<unknown>(keys.viewerView, null) === "full" ? "full" : "changes";
 }
+
+/** A cluster board's expansions ("N12:callers"), as this reader left them. */
+export function loadExpand(key: BoardKey): string[] {
+  const v = load<unknown>(keys.expand(key), []);
+  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && /^N\d+:(callers|callees)$/.test(x)) : [];
+}
```

`frontend/src/board/overview.ts`:

```ts
import type { ClusterInfo, Overview } from "./types";

/** The overview's layer bands (spec 2026-10-03-large-change-boards §5): each cluster in its layer, top layer first,
 * clusters without a layer in "other" at the bottom; layers without clusters are left out. */
export function bandsOf(ov: Overview): { level: number; name: string; clusters: ClusterInfo[] }[] {
  const levels = [...ov.layers].sort((a, b) => b.level - a.level);
  const other = levels.filter((l) => l.level < 0);
  return [...levels.filter((l) => l.level >= 0), ...other]
    .map((l) => ({ ...l, clusters: ov.clusters.filter((c) => (c.level ?? -1) === l.level) }))
    .filter((b) => b.clusters.length > 0);
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** A cluster's links in words, strongest first: "→ svc/logger: 22 calls, 3 shared fields" (it calls in) and
 * "← drv/uart: 9 calls" (it is called). `max` keeps the strongest few (phones). */
export function linkLines(ov: Overview, id: string, max = Infinity): string[] {
  const name = new Map(ov.clusters.map((c) => [c.id, c.name]));
  const lines = ov.links.filter((l) => l.src === id || l.dst === id).map((l) => {
    const out = l.src === id, other = name.get(out ? l.dst : l.src) ?? "?";
    const what = [l.calls ? plural(l.calls, "call", "calls") : "", l.fields ? plural(l.fields, "shared field", "shared fields") : ""]
      .filter(Boolean).join(", ");
    return { w: l.calls + l.fields, text: `${out ? "→" : "←"} ${other}: ${what}` };
  });
  return lines.sort((a, b) => b.w - a.w).slice(0, max).map((l) => l.text);
}

/** Clusters linked to `id` either way (outlined when it is selected). */
export function linkedTo(ov: Overview, id: string): Set<string> {
  return new Set(ov.links.flatMap((l) => (l.src === id ? [l.dst] : l.dst === id ? [l.src] : [])));
}

/** The previous or next cluster in risk order (‹ ›), wrapping around. */
export function stepCluster(ov: Overview, id: string, dir: 1 | -1): string {
  const i = ov.clusters.findIndex((c) => c.id === id), n = ov.clusters.length;
  return ov.clusters[((i < 0 ? 0 : i) + dir + n) % n].id;
}

/** The cluster whose changed code is in this depot file, or null. */
export function clusterOfFile(ov: Overview, path: string): string | null {
  return ov.clusters.find((c) => c.files.includes(path))?.id ?? null;
}
```

`frontend/src/board/Canvas.tsx`:

```diff
diff --git a/frontend/src/board/Canvas.tsx b/frontend/src/board/Canvas.tsx
index 81428f2..c310c23 100644
--- a/frontend/src/board/Canvas.tsx
+++ b/frontend/src/board/Canvas.tsx
@@ -15,6 +15,12 @@ interface Props {
   panBy: (dx: number, dy: number) => void;
   onOpenFile: (id: string) => void;
   onInteract: () => void;
+  /** "+N callers / +N callees" on nodes with more off the board (spec 2026-10-03-large-change-boards §3). */
+  onExpand?: (id: string, way: "callers" | "callees") => void;
+  /** A visitor's link to the board of the cluster it belongs to. */
+  onHome?: (cluster: string, id: string) => void;
+  /** A cluster id's name, for the visitor link. */
+  homeName?: (cluster: string) => string;
   /** Phone Map (spec §13.4): two-finger pinch, tap opens the code sheet, long-press before a node moves. */
   touch?: {
     onPinchStart: (mid: { x: number; y: number }) => void;
@@ -28,9 +34,10 @@ const LONG_PRESS = 450;
 const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed", signature: "Δ signature" } as const;
 
 /** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node sideways when dragged by it. */
-export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, onOpenFile, onInteract, touch }: Props) {
+export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, onOpenFile, onInteract, touch, onExpand,
+  onHome, homeName }: Props) {
   const root = useRef<HTMLDivElement>(null);
-  const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; go: boolean;
+  const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; go: boolean; act: string | null;
                         dragging: boolean; ox: number; oy: number; armed: boolean; timer: number } | null>(null);
   const pts = useRef(new Map<number, { x: number; y: number }>());     // touch: active pointers
   const pinch = useRef<{ d: number } | null>(null);
@@ -96,7 +103,8 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
         const t = e.target as HTMLElement, n = t.closest<HTMLElement>(".bd-node"), r = root.current!.getBoundingClientRect();
         const at = n?.dataset.id ? pos.get(n.dataset.id) : undefined;     // keep the grab point under the pointer
         const d = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
-                    node: n?.dataset.id ?? null, go: !!t.closest(".bd-go"), dragging: false,
+                    node: n?.dataset.id ?? null, go: !!t.closest(".bd-go"), act: t.closest<HTMLElement>("[data-act]")?.dataset.act ?? null,
+                    dragging: false,
                     ox: at ? at.x - (e.clientX - r.left) : 0, oy: at ? at.y - (e.clientY - r.top) : 0,
                     armed: !touch, timer: 0 };
         if (touch && d.node)                                 // touch: a node moves only after a long press
@@ -140,6 +148,12 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
         end();
         if (!d || d.dragging || !d.node) return;
         const n = byId.get(d.node);
+        if (d.act) {                                         // a badge or a visitor's home link, not the card
+          onInteract();
+          if (d.act === "home" && n?.home) onHome?.(n.home, d.node);
+          else if (d.act === "callers" || d.act === "callees") onExpand?.(d.node, d.act);
+          return;
+        }
         if (!n?.path || !n.range) return;
         onInteract();
         if (d.go) onOpenFile(d.node);
@@ -185,7 +199,7 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
         const p = pos.get(n.id);
         if (!p) return null;
         const card = state.cards[n.id], on = onPath.has(n.id);
-        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" ? "field" : "", on ? "onflow" : "",
+        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" ? "field" : "", on ? "onflow" : "", n.home ? "visitor" : "",
           !graph && !on && !n.change && !card ? "dim" : "", state.moved[state.layout][n.id] !== undefined ? "moved" : "",
           card ? "has-card" : "", n.id === front ? "front" : "", grab === n.id ? "grab" : ""].filter(Boolean).join(" ");
         const fx = badge.get(n.id);
@@ -199,6 +213,14 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
             {!n.change && n.warn > 0 && <span className="warn-dot">{n.warn}</span>}
             {n.path && n.range && <button className="bd-go" title="Open full file" aria-label={`Open ${n.label} in the file viewer`}>⤢</button>}
             {fx && landings.has(n.id) && <div className="fxbadge">⚠ {fx}</div>}
+            {n.home && onHome && <span className="bd-home" data-act="home" role="button" title={`Open ${n.home}'s board`}>
+              · {homeName?.(n.home) ?? n.home} ›</span>}
+            {onExpand && (!!n.more_callers || !!n.more_callees) && (
+              <span className="bd-more-nb">
+                {!!n.more_callers && <span data-act="callers" role="button" aria-label={`Add ${n.label}'s callers`}>+{n.more_callers} callers</span>}
+                {!!n.more_callees && <span data-act="callees" role="button" aria-label={`Add ${n.label}'s callees`}>+{n.more_callees} callees</span>}
+              </span>
+            )}
           </div>
         );
       })}
```

`frontend/src/board/Board.tsx`:

```diff
diff --git a/frontend/src/board/Board.tsx b/frontend/src/board/Board.tsx
index b6d50fc..50146d6 100644
--- a/frontend/src/board/Board.tsx
+++ b/frontend/src/board/Board.tsx
@@ -28,8 +28,29 @@ interface Props {
   focus?: string | null;
   /** Renders the review header (extra content to place in it, if any). */
   head: (extra: ReactNode) => ReactNode;
+  /** A cluster's board in a split review (spec 2026-10-03-large-change-boards §5): */
+  cluster?: {
+    /** Saved layout, moves and tabs are per cluster ("12.C3"). */
+    prefKey: string;
+    /** Breadcrumb and ‹ ›, shown in the header. */
+    nav: ReactNode;
+    /** Back to the overview ("Whole change" in the change panel). */
+    onWhole: () => void;
+    /** A visitor's link: open the board of the cluster it belongs to, focused on it. */
+    onHome: (cluster: string, id: string) => void;
+    homeName: (cluster: string) => string;
+    /** Every cluster, for the phone menu. */
+    list: { id: string; name: string }[];
+  };
+  /** A file to open in the viewer on arrival (the overview's file tree). */
+  openPath?: string | null;
+  /** "+N callers / +N callees"; with `onReset` when the reader has expanded the board. */
+  expansion?: { onExpand: (id: string, way: "callers" | "callees") => void; onReset: (() => void) | null };
 }
 
+/** Nodes a board draws before the reader expands it (backend `analysis.board_max_nodes`). */
+export const BUDGET = 30;
+
 const wideScreen = () => window.innerWidth > 1100;
 const PHONE = "(max-width: 640px)";
 
@@ -45,9 +66,12 @@ function usePhone() {
 }
 
 /** The review board (spec §2–§4): flow bar, lensed canvas with cards, file viewer and change panel. */
-export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head }: Props) {
+export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head: reviewHead, cluster, expansion,
+  openPath }: Props) {
+  const prefKey = cluster?.prefKey ?? reviewId;
+  const head = useCallback((extra: ReactNode) => reviewHead(<>{cluster?.nav}{extra}</>), [reviewHead, cluster?.nav]);
   const [state, dispatch] = useReducer(reduce, undefined, () => {
-    const s = { ...initialState(loadLens(), loadMovedAll(reviewId), loadLayout(reviewId) ?? (preferDepth(board) ? "depth" : "layers")),
+    const s = { ...initialState(loadLens(), loadMovedAll(prefKey), loadLayout(prefKey) ?? (preferDepth(board) ? "depth" : "layers")),
                 about: loadAboutOpen() ?? wideScreen() };        // change panel: remembered, else open on wide screens
     return board.flows.length ? s : { ...s, mode: "graph" as const };
   });
@@ -65,7 +89,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const [sheet, setSheet] = useState<string | null>(null);
   const anim = useRef(0);
 
-  useEffect(() => save(keys.moved(reviewId), state.moved), [reviewId, state.moved]);
+  useEffect(() => save(keys.moved(prefKey), state.moved), [prefKey, state.moved]);
   useEffect(() => save(keys.lens, state.view.lens), [state.view.lens]);
   useEffect(() => { const t = window.setTimeout(() => setHint(false), 7000); return () => window.clearTimeout(t); }, []);
   const interact = useCallback(() => setHint(false), []);
@@ -140,6 +164,12 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
     act({ t: "card.open", id: focus });
     panTo([focus]);
   }, [focus, vp.W, nodes, act, panTo]);
+  const opened = useRef<string | null>(null);         // the overview's file tree: open that file once
+  useEffect(() => {
+    if (!openPath || openPath === opened.current) return;
+    opened.current = openPath;
+    act({ t: "viewer.open", path: openPath, line: null, wide: wideScreen() });
+  }, [openPath, act]);
   const [showMap, setShowMap] = useState(0);           // phone: a citation shows the Map with the function's code sheet
   const sheetFor = useRef<string | null>(null);
   useEffect(() => {                                   // the effect above centres it once the Map has its size
@@ -151,7 +181,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const selectFlow = useCallback((i: number) => { act({ t: "flow", i }); panTo(board.flows[i].path); }, [act, panTo, board]);
   const setLayout = (layout: "layers" | "depth") => {
     if (layout === state.layout) return;
-    save(keys.layout(reviewId), layout);
+    save(keys.layout(prefKey), layout);
     act({ t: "layout", layout });
   };
   const relaid = useRef(state.layout);                // re-centre once the other layout's positions exist
@@ -191,14 +221,15 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const cardCount = Object.keys(state.cards).length;
   const canvas = vp.W > 0 && <>
     <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act}
-            panBy={panBy} onOpenFile={openFile} onInteract={interact}
+            panBy={panBy} onOpenFile={openFile} onInteract={interact} onExpand={expansion?.onExpand}
+            onHome={cluster?.onHome} homeName={cluster?.homeName}
             touch={phone ? { onPinchStart, onPinch, onTap: setSheet } : undefined} />
     {!phone && <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
                           comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />}
   </>;
   if (phone)
     return (
-      <PhoneBoard reviewId={reviewId} board={board} state={state} act={act} sources={sources} comments={comments}
+      <PhoneBoard reviewId={reviewId} board={board} state={state} act={act} sources={sources} comments={comments} clusters={cluster?.list}
                   onComments={onComments} risk={risk} sideEffects={sideEffects} head={head} onOpenFile={openFile}
                   showMap={showMap}
                   map={
@@ -216,7 +247,8 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
                onStep={(id) => act({ t: "card.toggle", id })} onStepOpen={openFile}
                height={flowH} onHeight={setFlowH} onHeightDone={(h) => { setFlowH(h); save(keys.flowH, h); }} />
       <div className={`bd-main${state.about ? " with-about" : ""}`}>
-        <ChangePanel open={state.about} onToggle={toggleAbout} reviewId={reviewId} comments={comments} onComments={onComments}
+        <ChangePanel open={state.about} onToggle={toggleAbout} reviewId={reviewId} prefKey={prefKey} onWhole={cluster?.onWhole}
+                     comments={comments} onComments={onComments}
                      layers={board.layers} about={board.about} sideEffects={sideEffects} risk={risk} openFiles={state.viewer.files} dispatch={act}
                      wide={wideScreen()} width={aboutW} onWidth={setAboutW} onWidthDone={(w) => save(keys.aboutW, w)} />
         <div className="bd-stage" ref={setStage}>
@@ -243,6 +275,10 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
                 ))}
               </span>
               {cardCount >= 2 && <button className="bd-ibtn float" onClick={() => act({ t: "card.closeAll" })}>Close all cards</button>}
+              {expansion?.onReset && (
+                <button className="bd-ibtn float over" title="Back to the board as built (you added callers or callees)"
+                        onClick={expansion.onReset}>{board.nodes.length} nodes · Reset</button>
+              )}
             </div>
             <div className="bd-legend">
               <span className="sw chg" />changed<span className="sw flow" />selected flow<span className="sw field" />field<span className="sw fx" />side effect
```

`frontend/src/board/ChangePanel.tsx`:

```diff
diff --git a/frontend/src/board/ChangePanel.tsx b/frontend/src/board/ChangePanel.tsx
index 64f94a4..532c74a 100644
--- a/frontend/src/board/ChangePanel.tsx
+++ b/frontend/src/board/ChangePanel.tsx
@@ -4,7 +4,7 @@ import Comments from "../components/Comments";
 import type { Action } from "./reducer";
 import type { AffectedDir } from "./sideEffects";
 import { driftSummary } from "./drift";
-import { keys, loadPanelTab, type PanelTab, save } from "./prefs";
+import { type BoardKey, keys, loadPanelTab, type PanelTab, save } from "./prefs";
 import Resizer from "./Resizer";
 import type { About } from "./types";
 
@@ -26,15 +26,19 @@ interface Props {
   onWidthDone: (w: number) => void;
   /** Phone Summary tab: always open, fills its tab, no toggle or resize grip. */
   embedded?: boolean;
+  /** Whose saved tab (a cluster's board has its own); defaults to the review. */
+  prefKey?: BoardKey;
+  /** A cluster's board: back to the whole change's overview. */
+  onWhole?: () => void;
 }
 
 /** "What's this change?" (spec §3.6): files tree first, then intent, why it's risky, changelists. Pushes the board. */
 export default function ChangePanel({ open, onToggle, reviewId, comments, onComments, layers, about, sideEffects, risk, openFiles,
-  dispatch, wide, width, onWidth, onWidthDone, embedded }: Props) {
+  dispatch, wide, width, onWidth, onWidthDone, embedded, prefKey = reviewId, onWhole }: Props) {
   const [shut, setShut] = useState<Set<string>>(new Set());
-  const [tab, setTab] = useState<PanelTab>(() => loadPanelTab(reviewId));
+  const [tab, setTab] = useState<PanelTab>(() => loadPanelTab(prefKey));
   const [openCls, setOpenCls] = useState<Set<number>>(new Set());
-  const chooseTab = (t: PanelTab) => { setTab(t); save(keys.panelTab(reviewId), t); };
+  const chooseTab = (t: PanelTab) => { setTab(t); save(keys.panelTab(prefKey), t); };
   if (!open && !embedded)
     return (
       <aside className="bd-about collapsed" onClick={onToggle}>
@@ -52,6 +56,7 @@ export default function ChangePanel({ open, onToggle, reviewId, comments, onComm
         {!embedded && <button className="bd-ibtn toggle" title="Collapse" aria-label="Collapse change summary" onClick={onToggle}>‹</button>}
         {risk && <span className={`bd-pill ${risk}`}>{risk.toUpperCase()} RISK</span>}
         <h2>What this change is trying to do</h2>
+        {onWhole && <button className="link small bd-whole" onClick={onWhole}>Whole change ›</button>}
         <p>{about.cls.map((c) => `CL ${c.cl}`).join(" · ")} · {nFiles} files · {about.intent_source === "llm"
           ? "summarised from the CL descriptions, the diff and the analysis" : "from the CL descriptions and the analysis"}</p>
       </div>
```

`frontend/src/board/phone/PhoneBoard.tsx`:

```diff
diff --git a/frontend/src/board/phone/PhoneBoard.tsx b/frontend/src/board/phone/PhoneBoard.tsx
index 0074ef0..7a1b824 100644
--- a/frontend/src/board/phone/PhoneBoard.tsx
+++ b/frontend/src/board/phone/PhoneBoard.tsx
@@ -29,6 +29,8 @@ interface Props {
   map: ReactNode;
   /** Bumped by Board to show the Map (a cited function opens there). */
   showMap: number;
+  /** A split review's clusters: the menu lists the overview and each cluster's board. */
+  clusters?: { id: string; name: string }[];
 }
 
 const TABS: [PhoneTab, string, string][] = [["flows", "☰", "Flows"], ["map", "◎", "Map"], ["files", "▤", "Files"], ["summary", "✦", "Summary"]];
@@ -56,6 +58,8 @@ export default function PhoneBoard(p: Props) {
           <NavLink to="/">All reviews</NavLink>
           <NavLink to={`/r/${reviewId}/findings`}>Findings</NavLink>
           <NavLink to={`/r/${reviewId}/cls`}>CLs &amp; Swarm</NavLink>
+          {p.clusters && <NavLink end to={`/r/${reviewId}`}>Overview</NavLink>}
+          {p.clusters?.map((c) => <NavLink key={c.id} to={`/r/${reviewId}/c/${c.id}`}>{c.id} · {c.name}</NavLink>)}
           {ai?.view?.llm && <button className="link" onClick={() => ai.setUsageOpen(true)}>AI usage</button>}
           <span onClick={(e) => e.stopPropagation()}><ThemeSwitch /></span>
           <button className="link" onClick={() => api.logout().then(() => window.location.assign("/login"))}>Log out</button>
```

`frontend/src/board/OverviewPage.tsx`:

```tsx
import { type ReactNode, useState } from "react";
import type { Comment } from "../api";
import "./board.css";
import ChangePanel from "./ChangePanel";
import { bandsOf, clusterOfFile, linkedTo, linkLines } from "./overview";
import { keys, loadAboutOpen, loadWidth, save } from "./prefs";
import type { Action } from "./reducer";
import type { Overview } from "./types";

interface Props {
  reviewId: number;
  ov: Overview;
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  head: (extra: ReactNode) => ReactNode;
  /** Open a cluster's board, optionally with a file open in its viewer. */
  onOpen: (cluster: string, file?: string) => void;
}

/** A split review's overview (spec 2026-10-03-large-change-boards §5): the clusters in the layer bands, with their risk,
 * counts and links; the whole change's summary beside them. */
export default function OverviewPage({ reviewId, ov, comments, onComments, risk, head, onOpen }: Props) {
  const [sel, setSel] = useState<string | null>(null);
  const [about, setAbout] = useState(() => loadAboutOpen() ?? window.innerWidth > 1100);
  const [aboutW, setAboutW] = useState(() => loadWidth(keys.aboutW, 360));
  const lit = sel ? linkedTo(ov, sel) : new Set<string>();
  const t = ov.totals;
  const dispatch = (a: Action) => {                       // the panel's file tree opens the file's cluster board
    if (a.t !== "viewer.open") return;
    const c = clusterOfFile(ov, a.path);
    if (c) onOpen(c, a.path);
  };
  return (
    <div className="bd ov-page">
      {head(<span className="bd-pill ghost">{t.files} files · {t.clusters} clusters · {t.flows} flows · {t.findings} findings</span>)}
      <div className={`bd-main${about ? " with-about" : ""}`}>
        <ChangePanel open={about} onToggle={() => { save(keys.about, !about); setAbout(!about); }} reviewId={reviewId}
                     comments={comments} onComments={onComments} layers={ov.layers} about={ov.about} sideEffects={[]} risk={risk}
                     openFiles={[]} dispatch={dispatch} wide={window.innerWidth > 1100} width={aboutW} onWidth={setAboutW}
                     onWidthDone={(w) => save(keys.aboutW, w)} />
        <div className="ov-bands" aria-label="Clusters">
          <p className="ov-lead">This change is split into {t.clusters} parts of connected code, riskiest first. Select one to see what
            it's linked to; open it for its board.{ov.merged_over_limit > 0 && ` ${ov.merged_over_limit} small parts were merged to keep the list short.`}</p>
          {bandsOf(ov).map((b) => (
            <section key={b.level} className={`ov-band lv${b.level < 0 ? "x" : b.level % 4}`} aria-label={`Layer ${b.name}`}>
              <h3>{b.name}</h3>
              <div className="ov-blocks">
                {b.clusters.map((c) => (
                  <div key={c.id} role="button" tabIndex={0} aria-pressed={sel === c.id} data-cluster={c.id}
                       className={`ov-block ${c.risk ?? "none"}${sel === c.id ? " sel" : ""}${lit.has(c.id) ? " lit" : ""}`}
                       onClick={() => setSel(sel === c.id ? null : c.id)} onDoubleClick={() => onOpen(c.id)}
                       onKeyDown={(e) => { if (e.key === "Enter") onOpen(c.id); }}>
                    <button className="ov-open" onClick={(e) => { e.stopPropagation(); onOpen(c.id); }}
                            aria-label={`Open ${c.name}`}>Open ›</button>
                    <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
                    <div className="ct"><span className="files-count">{c.files.length} files · </span>{c.changed} changed · {c.flows} flows
                      {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
                    {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
                    {c.also.length > 0 && (
                      <div className="also">also in {c.also.map((lv) => ov.layers.find((l) => l.level === lv)?.name ?? `L${lv}`).join(", ")}</div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
```

`frontend/src/board/ClusterBoard.tsx`:

```tsx
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Comment, type FileChange } from "../api";
import Board from "./Board";
import { stepCluster } from "./overview";
import { keys, loadExpand, save } from "./prefs";
import type { Board as BoardModel, Overview } from "./types";

interface Props {
  reviewId: number;
  ov: Overview;
  cid: string;
  files: FileChange[];
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  head: (extra: ReactNode) => ReactNode;
  /** Bumped when an AI explanation finished: the board is fetched again. */
  reload: number;
}

/** One cluster's board in a split review (spec 2026-10-03-large-change-boards §5): breadcrumb and ‹ ›, visitors
 * linking to their clusters, "+N callers" expansions kept in the page address (and remembered per cluster). */
export default function ClusterBoard({ reviewId, ov, cid, files, comments, onComments, risk, head, reload }: Props) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const prefKey = `${reviewId}.${cid}`;
  const fromUrl = params.get("x");
  const expand = useMemo(() => (fromUrl !== null ? fromUrl.split(",").filter(Boolean) : loadExpand(prefKey)), [fromUrl, prefKey]);
  const [board, setBoard] = useState<BoardModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.board(reviewId, cid, expand).then((b) => { if (live) { setBoard(b); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [reviewId, cid, expand, reload]);
  const setExpand = useCallback((next: string[]) => {
    save(keys.expand(prefKey), next);
    const p = new URLSearchParams(params);
    p.delete("node");
    if (next.length) p.set("x", next.join(",")); else p.delete("x");
    setParams(p, { replace: true });
  }, [params, prefKey, setParams]);
  const info = ov.clusters.find((c) => c.id === cid);
  const name = useCallback((id: string) => ov.clusters.find((c) => c.id === id)?.name ?? id, [ov]);
  const go = (to: string) => navigate(`/r/${reviewId}/c/${to}`);
  const nav = (
    <span className="bd-crumb">
      <Link to={`/r/${reviewId}`}>Overview</Link> › <b>{info?.name ?? cid}</b>
      <button className="bd-ibtn" aria-label="Previous cluster" onClick={() => go(stepCluster(ov, cid, -1))}>‹</button>
      <span className="pos">{cid} of {ov.clusters.length}</span>
      <button className="bd-ibtn" aria-label="Next cluster" onClick={() => go(stepCluster(ov, cid, 1))}>›</button>
    </span>
  );
  const cluster = {
    prefKey, nav, homeName: name,
    onWhole: () => navigate(`/r/${reviewId}`),
    onHome: (c: string, node: string) => navigate(`/r/${reviewId}/c/${c}?node=${encodeURIComponent(node)}`),
    list: ov.clusters.map((c) => ({ id: c.id, name: c.name })),
  };
  if (error)
    return (
      <main className="page">
        <div className="banner warn">{error} <Link to={`/r/${reviewId}`}>Back to the overview</Link></div>
      </main>
    );
  if (!board) return <main className="page muted">Loading {info?.name ?? cid}…</main>;
  return (
    <main className="review board">
      <Board key={cid} reviewId={reviewId} board={board} files={files} comments={comments} onComments={onComments} risk={risk}
             focus={params.get("node")} openPath={params.get("file")} head={head} cluster={cluster}
             expansion={{ onExpand: (id, way) => setExpand([...expand.filter((x) => x !== `${id}:${way}`), `${id}:${way}`]),
                          onReset: expand.length ? () => setExpand([]) : null }} />
    </main>
  );
}
```

`frontend/src/pages/Review.tsx`:

```diff
diff --git a/frontend/src/pages/Review.tsx b/frontend/src/pages/Review.tsx
index 1f9f7ab..32d261a 100644
--- a/frontend/src/pages/Review.tsx
+++ b/frontend/src/pages/Review.tsx
@@ -1,8 +1,10 @@
 import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
 import { Navigate, NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
-import { api, ApiError, type AiJob, type Board as BoardModel, type Comment, type FileChange, type Finding, type ReviewDetail } from "../api";
+import { api, ApiError, type AiJob, type Board as BoardModel, type Comment, type FileChange, type Finding, type Overview, type ReviewDetail } from "../api";
 import { useMe } from "../App";
 import Board from "../board/Board";
+import ClusterBoard from "../board/ClusterBoard";
+import OverviewPage from "../board/OverviewPage";
 import { driftSummary } from "../board/drift";
 import AiPill from "../components/AiPill";
 import ClsPanel from "../components/ClsPanel";
@@ -19,6 +21,8 @@ export default function Review() {
   const [params] = useSearchParams();
   const [detail, setDetail] = useState<ReviewDetail | null>(null);
   const [board, setBoard] = useState<BoardModel | null | undefined>(undefined);   // null: no board for this review
+  const [overview, setOverview] = useState<Overview | null | undefined>(undefined);  // a split review's (null: one board)
+  const [reload, setReload] = useState(0);              // cluster boards fetch again after an AI explanation
   const [findings, setFindings] = useState<Finding[]>([]);
   const [files, setFiles] = useState<FileChange[]>([]);
   const [comments, setComments] = useState<Comment[]>([]);
@@ -29,7 +33,11 @@ export default function Review() {
   const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
   const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
   const loadResults = useCallback(() => Promise.all([
-    api.board(id).then(setBoard).catch((e) => { if (e instanceof ApiError && e.status === 404) setBoard(null); else throw e; }),
+    api.overview(id).then((ov) => { setOverview(ov); setBoard(null); }).catch((e) => {
+      if (!(e instanceof ApiError && e.status === 404)) throw e;
+      setOverview(null);
+      return api.board(id).then(setBoard).catch((e2) => { if (e2 instanceof ApiError && e2.status === 404) setBoard(null); else throw e2; });
+    }),
     loadFindings(), api.files(id).then(setFiles), loadComments(),
   ]).catch((e) => setError(String(e.message ?? e))), [id, loadFindings, loadComments]);
 
@@ -53,9 +61,12 @@ export default function Review() {
   const people = useMemo(() => [...new Set([detail?.review.created_by ?? "", ...comments.map((c) => c.author)])].filter(Boolean),
                          [detail, comments]);
   const onAiDone = useCallback((jobs: AiJob[]) => {   // an explanation finished: show it
-    if (jobs.some((j) => j.kind === "flow")) api.board(id).then(setBoard).catch(() => {});
+    if (jobs.some((j) => j.kind === "flow")) {
+      if (overview) setReload((k) => k + 1);
+      else api.board(id).then(setBoard).catch(() => {});
+    }
     if (jobs.some((j) => j.kind === "finding")) loadFindings();
-  }, [id, loadFindings]);
+  }, [id, loadFindings, overview]);
   const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
 
   const onCite = useCallback((cite: string) => {
@@ -104,20 +115,31 @@ export default function Review() {
   return (
     <AiProvider value={ai}>
     <Routes>
-      <Route index element={board ? (
+      <Route index element={overview ? (
+        params.get("node") ? <Locate reviewId={id} node={params.get("node")!} /> : (
+          <main className="review board">
+            <OverviewPage reviewId={id} ov={overview} comments={comments} onComments={loadComments} risk={r.risk} head={head}
+                          onOpen={(c, file) => navigate(`/r/${id}/c/${c}${file ? `?file=${encodeURIComponent(file)}` : ""}`)} />
+          </main>
+        )
+      ) : board ? (
         <main className="review board">
           <Board reviewId={id} board={board} files={files} comments={comments} onComments={loadComments} risk={r.risk}
                  focus={params.get("node")} head={head} />
         </main>
-      ) : page(board === undefined ? <p className="muted">Loading…</p> : (
+      ) : page(board === undefined || overview === undefined ? <p className="muted">Loading…</p> : (
         <div className="banner warn">
           No review board for this review (see the stage notes above; reviews made before the board existed have none).
           {me?.is_owner ? " Re-run it to build one." : " The owner can re-run it to build one."} Findings and CLs are still available.
           {me?.is_owner && <> <button onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button></>}
         </div>
       ))} />
+      <Route path="c/:cid" element={overview ? (
+        <ClusterRoute reviewId={id} ov={overview} files={files} comments={comments} onComments={loadComments} risk={r.risk}
+                      head={head} reload={reload} />
+      ) : page(<p className="muted">{overview === null ? "This review is shown as one board." : "Loading…"}</p>)} />
       <Route path="findings" element={page(
-        <Findings reviewId={id} findings={findings} focus={focus} comments={comments}
+        <Findings reviewId={id} findings={findings} focus={focus} comments={comments} groups={overview?.clusters}
                   onComments={loadComments} onFindings={loadFindings} onCite={onCite} />)} />
       <Route path="files" element={<Navigate to={`/r/${id}`} replace />} />
       <Route path="cls" element={page(<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />)} />
@@ -125,3 +147,21 @@ export default function Review() {
     </AiProvider>
   );
 }
+
+/** `/r/:id?node=N12` on a split review: open the board of the cluster that shows the node. */
+function Locate({ reviewId, node }: { reviewId: number; node: string }) {
+  const navigate = useNavigate();
+  const [missing, setMissing] = useState(false);
+  useEffect(() => {
+    api.locate(reviewId, { node }).then(({ cluster }) => {
+      if (cluster) navigate(`/r/${reviewId}/c/${cluster}?node=${encodeURIComponent(node)}`, { replace: true });
+      else setMissing(true);
+    }).catch(() => setMissing(true));
+  }, [reviewId, node, navigate]);
+  return <main className="page muted">{missing ? `${node} isn't on any board of this review.` : `Finding ${node}…`}</main>;
+}
+
+function ClusterRoute(p: Omit<Parameters<typeof ClusterBoard>[0], "cid">) {
+  const cid = useParams().cid!;
+  return <ClusterBoard key={cid} {...p} cid={cid} />;
+}
```

`frontend/src/components/Findings.tsx`:

```diff
diff --git a/frontend/src/components/Findings.tsx b/frontend/src/components/Findings.tsx
index a4bad85..8bcab80 100644
--- a/frontend/src/components/Findings.tsx
+++ b/frontend/src/components/Findings.tsx
@@ -1,5 +1,6 @@
-import { useEffect, useRef } from "react";
+import { useEffect, useRef, useState } from "react";
 import { api, type Comment, type Finding } from "../api";
+import type { ClusterInfo } from "../board/types";
 import { useMe } from "../App";
 import { SeverityBadge } from "./Badges";
 import CiteText, { CiteList } from "./CiteText";
@@ -14,15 +15,39 @@ interface Props {
   onComments: () => void;
   onFindings: () => void;
   onCite: (id: string) => void;
+  /** A split review's clusters: findings are grouped under them (spec 2026-10-03-large-change-boards §5). */
+  groups?: ClusterInfo[];
 }
 
-export default function Findings({ reviewId, findings, focus, comments, onComments, onFindings, onCite }: Props) {
+export default function Findings({ reviewId, findings, focus, comments, onComments, onFindings, onCite, groups }: Props) {
   const me = useMe();
   const refs = useRef(new Map<string, HTMLElement>());
+  const [only, setOnly] = useState<string>("all");
   useEffect(() => {
     if (focus) refs.current.get(focus)?.scrollIntoView({ behavior: "smooth", block: "start" });
   }, [focus]);
   if (!findings.length) return <p className="muted">No findings.</p>;
+  if (groups) {
+    const homed = new Set(groups.flatMap((g) => g.finding_ids));
+    const sections = [...groups.map((g) => ({ id: g.id, name: g.name, fs: findings.filter((f) => g.finding_ids.includes(f.id)) })),
+                      { id: "rest", name: "The whole change", fs: findings.filter((f) => !homed.has(f.id)) }]
+      .filter((s) => s.fs.length && (only === "all" || only === s.id));
+    return (
+      <div className="findings grouped">
+        <label className="fg-filter">Show <select value={only} onChange={(e) => setOnly(e.target.value)} aria-label="Findings of">
+          <option value="all">every part</option>
+          {groups.filter((g) => g.finding_ids.length).map((g) => <option key={g.id} value={g.id}>{g.id} · {g.name}</option>)}
+        </select></label>
+        {sections.map((s) => (
+          <section key={s.id} className="fg" aria-label={`Findings in ${s.name}`}>
+            <h2>{s.id !== "rest" && <span className="fg-id">{s.id}</span>} {s.name} <span className="muted small">{s.fs.length}</span></h2>
+            <Findings reviewId={reviewId} findings={s.fs} focus={focus} comments={comments} onComments={onComments}
+                      onFindings={onFindings} onCite={onCite} />
+          </section>
+        ))}
+      </div>
+    );
+  }
   return (
     <div className="findings">
       {findings.map((f) => (
```

`frontend/src/board/board.css`:

```diff
diff --git a/frontend/src/board/board.css b/frontend/src/board/board.css
index 50a9d87..b865047 100644
--- a/frontend/src/board/board.css
+++ b/frontend/src/board/board.css
@@ -152,7 +152,7 @@ body.bd-resizing-v, body.bd-resizing-v * { cursor: row-resize !important; user-s
 .bd-node:hover .bd-go, .bd-node.chg .bd-go, .bd-node.has-card .bd-go { opacity: 1; }
 
 /* toolbar, legend, hint */
-.bd-tools { position: absolute; left: 12px; top: 12px; z-index: 45; display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
+.bd-tools { position: absolute; left: 12px; top: 12px; z-index: 51; display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
   max-width: calc(100% - 24px); pointer-events: none; }
 .bd-tools > * { pointer-events: auto; }
 .bd-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
@@ -344,3 +344,58 @@ details.bd-drift { padding: 6px 10px; font-size: 12px; } details.bd-drift summar
 details.bd-drift.info { background: var(--bd-sunken); border-left-color: var(--bd-line); color: var(--bd-muted); }
 .bd-about .cl .head { display: block; text-align: left; padding: 0; border: 0; background: none; cursor: pointer; width: 100%; }
 .bd-about .cl .first { margin-top: 3px; font-size: 12.5px; }
+
+/* ---- large changes: overview, cluster boards (spec 2026-10-03-large-change-boards §5) ---- */
+.ov-page .bd-main { overflow: hidden; }
+.ov-bands { flex: 1; overflow: auto; padding: 14px 18px 40px; background: var(--bd-bg); color: var(--bd-ink); }
+.ov-lead { margin: 0 0 12px; color: var(--bd-muted); font: 13px var(--bd-sans); max-width: 760px; }
+.ov-band { display: flex; gap: 10px; align-items: stretch; padding: 10px; border-radius: 10px; margin-bottom: 8px;
+  background: var(--bd-band); border: 1px solid var(--bd-rule); }
+.ov-band.lv0 { background: color-mix(in srgb, var(--ok-bg) 70%, transparent); }
+.ov-band.lv1 { background: color-mix(in srgb, var(--chg-bg-soft) 70%, transparent); }
+.ov-band.lv2 { background: color-mix(in srgb, var(--bd-sel) 70%, transparent); }
+.ov-band.lv3 { background: color-mix(in srgb, var(--ctx-bg-soft) 80%, transparent); }
+.ov-band h3 { width: 92px; flex: none; margin: 4px 0 0; font: 700 11px var(--bd-sans); letter-spacing: .06em;
+  text-transform: uppercase; color: var(--bd-band-label); }
+.ov-blocks { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; }
+.ov-block { flex: 1 1 240px; max-width: 360px; background: var(--bd-surface); border: 2px solid var(--bd-node-line); border-radius: 10px;
+  padding: 8px 10px; font: 12px var(--bd-sans); cursor: pointer; position: relative; }
+.ov-block:hover { border-color: var(--bd-node-line-hover); }
+.ov-block.high { border-color: var(--fx); } .ov-block.medium { border-color: var(--chg); }
+.ov-block.sel { box-shadow: 0 0 0 4px var(--flow-glow); }
+.ov-block.lit { outline: 2px dashed var(--flow); outline-offset: 2px; }
+.ov-block .nm { font: 700 13px var(--bd-mono); margin-right: 56px; }
+.ov-block .ct { color: var(--bd-muted); margin: 3px 0; }
+.ov-block .ln { color: var(--ctx-ink); }
+.ov-block .also { color: var(--chg-ink); font-style: italic; margin-top: 2px; }
+.ov-block .ov-open { position: absolute; right: 8px; top: 7px; border: 0; background: none; color: var(--flow); font: 600 12px var(--bd-sans);
+  cursor: pointer; }
+.ov-block .sev, .fg .sev { font: 700 10px var(--bd-sans); padding: 1px 6px; border-radius: 4px; color: #fff; vertical-align: 1px; }
+.ov-block .sev.high { background: var(--fx); } .ov-block .sev.medium { background: var(--chg-deep); }
+.ov-block .sev.low { background: var(--ok); } .ov-block .sev.info { background: var(--info); }
+.bd-crumb { display: inline-flex; gap: 6px; align-items: center; font: 13px var(--bd-sans); color: #dfe0ff; }
+.bd-crumb a { color: #c9c2ff; } .bd-crumb .pos { font-size: 11px; opacity: .8; }
+.bd-crumb .bd-ibtn { padding: 0 7px; }
+.bd-whole { margin-left: 8px; }
+.bd-node.visitor { border-style: dashed; border-color: var(--flow); background: var(--bd-sel); }
+.bd-node.visitor.chg { border-style: dashed; border-color: var(--flow); }
+.bd-node .bd-home { margin-left: 6px; font: 600 10.5px var(--bd-sans); color: var(--flow); cursor: pointer; }
+.bd-node .bd-more-nb { position: absolute; left: 50%; top: 100%; transform: translateX(-50%); margin-top: 4px; display: flex; gap: 4px;
+  white-space: nowrap; }
+.bd-node .bd-more-nb span { font: 600 10px var(--bd-sans); color: var(--ctx-ink); background: var(--ctx-bg-soft);
+  border: 1px solid var(--ctx-bg); border-radius: 99px; padding: 0 6px; cursor: pointer; }
+.bd-node .bd-more-nb span:hover { background: var(--ctx-bg); }
+.bd-ibtn.over { border-color: var(--flow); color: var(--flow); }
+.findings.grouped .fg h2 { font-size: 15px; margin: 18px 0 6px; display: flex; gap: 8px; align-items: baseline; }
+.findings.grouped .fg-id { font: 700 11px var(--bd-mono); color: var(--flow); }
+.fg-filter { display: inline-flex; gap: 6px; align-items: center; font-size: 13px; }
+@media (max-width: 640px) {
+  .ov-page .bd-about { display: none; }
+  .ov-bands { padding: 10px 10px 30px; }
+  .ov-band { flex-direction: column; gap: 6px; padding: 8px; }
+  .ov-band h3 { width: auto; margin: 0; }
+  .ov-blocks { flex-direction: column; }
+  .ov-block { max-width: none; flex: none; width: 100%; box-sizing: border-box; }
+  .ov-block .files-count, .ov-block .ln:nth-of-type(n+5) { display: none; }
+  .bd-crumb .pos { display: none; }
+}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/overview.test.ts && npx tsc --noEmit && npm run build && npx playwright test e2e/large.spec.ts`
Expected: `Tests  6 passed (6)` and `✓ built in …` and `7 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test`
Expected: `Tests  91 passed (91)`, no `tsc` output, `✓ built in …` and `43 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/types.ts frontend/src/api.ts frontend/src/board/prefs.ts frontend/src/board/overview.ts frontend/src/board/Canvas.tsx frontend/src/board/Board.tsx frontend/src/board/ChangePanel.tsx frontend/src/board/phone/PhoneBoard.tsx frontend/src/board/OverviewPage.tsx frontend/src/board/ClusterBoard.tsx frontend/src/pages/Review.tsx frontend/src/components/Findings.tsx frontend/src/board/board.css frontend/src/board/overview.test.ts frontend/e2e/serve-large.sh frontend/playwright.config.ts frontend/e2e/large.spec.ts
git commit -m "feat(ui): the overview, cluster boards with visitors and expansion, findings by cluster"
```

---

### Task 5: The lab: libgit2's large commits as Perforce changelists

Spec §7. `lab/p4-import.py` (run by hand, never as a service) builds a Perforce history from a git project: the base
snapshot, then for each chosen commit a catch-up changelist ("catch-up to <sha>") and the commit as one changelist
("<subject> (upstream <sha>)"); `--shelve` commits become pending changelists shelved on top of head. The default
picks first-parent commits touching at least `--min-files` (30) C/C++ files outside tests; `--list` prints them and
stops. Adds, deletes, renames, binaries, symlinks and executable bits are handled; paths with `@#%*` are escaped;
p4 commands are batched; the client uses `allwrite` and `rmdir`. If no server answers at `--port` and `--root` is
given, it starts `p4d` in the background (writing `p4d.pid`), sets the first user's password like `lab/setup.sh` and
says how to stop it. It refuses a depot path that already has files. `cls.tsv` lists every changelist (number, kind,
sha, subject, C files and directories outside tests). `lab/build.sh` takes `WS` and `BUILD` for the second workspace;
the lab README says how to import, build and review libgit2-big. The import test runs only when `p4` and `p4d` are on
PATH (the lab's `bin`).

**Files:**
- Create: `lab/p4-import.py`
- Modify: `lab/build.sh`
- Modify: `lab/README.md`
- Test: `backend/tests/test_lab_import.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (a standalone script; the lab's `p4`/`p4d` binaries).
- Produces: `lab/p4-import.py --repo --clone --base --end --commits --min-files --shelve --exclude --list --depot
  --workspace --client --port --root --password --out`; `cls.tsv` columns `cl kind sha subject c_files dirs`, kinds
  `base`, `catch-up`, `commit`, `shelved`; `lab/build.sh` env `WS`, `BUILD`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_lab_import.py`:

```python
"""lab/p4-import.py builds a Perforce history from a git project (spec 2026-10-03-large-change-boards §7)."""
import csv
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "lab" / "p4-import.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def write(repo: Path, path: str, text: str | bytes, exe: bool = False) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text if isinstance(text, bytes) else text.encode())
    p.chmod(0o755 if exe else 0o644)


@pytest.fixture
def project(tmp_path):
    """A base, a small commit, a large one (31 new C files in two directories, a rename, a delete, a binary, an
    executable bit dropped, a file with '@' in its name edited) and a small one to shelve."""
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q", "-b", "main")
    git(src, "config", "user.email", "lab@example.com")
    git(src, "config", "user.name", "lab")
    for i in range(5):
        write(src, f"src/a/f{i}.c", f"int f{i}(void) {{ return {i}; }}\n")
    write(src, "include/x.h", "int f0(void);\n")
    write(src, "tests/test_a.c", "int test_a(void) { return 0; }\n")
    write(src, "tests/resources/blob.bin", b"\0\1\2")
    write(src, "tools/run.sh", "#!/bin/sh\necho run\n", exe=True)
    write(src, "docs/readme.txt", "hello\n")
    base = commit(src, "base")
    write(src, "src/a/f0.c", "int f0(void) { return 10; }\n")
    (src / "docs/readme.txt").unlink()
    write(src, "src/a/at@sign.c", "int at(void) { return 1; }\n")
    small = commit(src, "small: tidy f0")
    for i in range(16):
        write(src, f"src/b/g{i}.c", f"int g{i}(void) {{ return {i}; }}\n")
    for i in range(15):
        write(src, f"src/c/h{i}.c", f"int h{i}(void) {{ return {i}; }}\n")
    write(src, "include/x.h", "int f0(void);\nint g0(void);\n")
    git(src, "mv", "src/a/f2.c", "src/c/moved.c")
    (src / "src/a/f3.c").unlink()
    write(src, "src/b/logo.png", b"\x89PNG\r\n\x1a\n\0\0\0binary")
    write(src, "tools/run.sh", "#!/bin/sh\necho run\n")
    write(src, "src/a/at@sign.c", "int at(void) { return 2; }\n")
    write(src, "tests/resources/blob.bin", b"\0\1\2\3")
    large = commit(src, "large: add the b and c modules")
    write(src, "src/b/g0.c", "int g0(void) { return 100; }\n")
    write(src, "src/d/new.c", "int nw(void) { return 0; }\n")
    (src / "src/a/f1.c").unlink()
    shelved = commit(src, "shelved: try g0 = 100")
    return src, base, small, large, shelved


def run(*args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=300)


def test_list_picks_first_parent_commits_touching_enough_c_files_outside_tests(project):
    src, base, small, large, shelved = project
    r = run("--repo", str(src), "--base", base, "--end", "main", "--list")
    assert r.returncode == 0, r.stderr
    rows = [line.split("\t") for line in r.stdout.strip().splitlines()]
    assert [row[0] for row in rows] == [large[:9]]
    assert rows[0][1:3] == ["36", "4"]                           # C files outside tests, their directories
    r = run("--repo", str(src), "--base", base, "--end", "main", "--list", "--min-files", "1")
    assert [line.split("\t")[0] for line in r.stdout.strip().splitlines()] == [small[:9], large[:9], shelved[:9]]


needs_p4d = pytest.mark.skipif(not (shutil.which("p4d") and shutil.which("p4")), reason="p4 and p4d are not on PATH")


@needs_p4d
def test_import_into_a_throwaway_p4d_with_catch_up_and_a_shelve(project, tmp_path):
    src, base, small, large, shelved = project
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = f"127.0.0.1:{s.getsockname()[1]}"
    root, ws, out = tmp_path / "p4root", tmp_path / "ws", tmp_path / "cls.tsv"
    env = {k: v for k, v in os.environ.items() if not k.startswith("P4")} | {"P4USER": "lab", "P4TICKETS": str(tmp_path / "t")}
    try:
        r = run("--repo", str(src), "--base", base, "--end", "main", "--depot", "//depot/proj", "--workspace", str(ws),
                "--client", "proj-ws", "--port", port, "--root", str(root), "--exclude", "tests/resources",
                "--shelve", shelved[:9], "--out", str(out), env=env)
        assert r.returncode == 0, r.stdout + r.stderr

        def p4(*a: str) -> str:
            return subprocess.run(["p4", "-p", port, "-c", "proj-ws", *a], check=True, capture_output=True, text=True,
                                  env=env).stdout

        # by client: a change holding only shelved files matches no depot path
        changes = p4("-ztag", "-F", "%change%\t%status%\t%desc%", "changes", "-l", "-c", "proj-ws").splitlines()
        changes = [c for c in changes if c.strip()]                    # a long description ends in a blank line
        assert [c.split("\t", 2)[1:] for c in reversed(changes)] == [
            ["submitted", f"import at upstream {base[:9]}"],
            ["submitted", f"catch-up to {large[:9]}"],
            ["submitted", f"large: add the b and c modules (upstream {large[:9]})"],
            ["pending", f"shelved: try g0 = 100 (upstream {shelved[:9]})"]]
        heads = dict(line.split("\t") for line in
                     p4("-ztag", "-F", "%depotFile%\t%headAction%", "fstat", "//depot/proj/...").strip().splitlines())
        assert heads["//depot/proj/docs/readme.txt"] == "delete" and heads["//depot/proj/src/a/f2.c"] == "delete"
        assert heads["//depot/proj/src/c/moved.c"] == "add" and heads["//depot/proj/src/a/at%40sign.c"] == "edit"
        assert not any("tests/resources" in f for f in heads) and "//depot/proj/tests/test_a.c" in heads
        assert p4("print", "-q", "//depot/proj/include/x.h") == "int f0(void);\nint g0(void);\n"
        assert p4("print", "-q", "//depot/proj/src/a/at%40sign.c") == "int at(void) { return 2; }\n"
        types = lambda f: p4("-ztag", "-F", "%headType%", "fstat", f).strip()      # noqa: E731
        assert "binary" in types("//depot/proj/src/b/logo.png")
        mods = lambda f: types(f).partition("+")[2]                                # noqa: E731
        assert "x" in mods("//depot/proj/tools/run.sh#1") and "x" not in mods("//depot/proj/tools/run.sh")
        pending = changes[0].split("\t")[0]
        files = re.findall(r"^\.\.\. (//\S+)#\d+ (\w+)", p4("describe", "-S", "-s", pending), re.M)
        assert sorted(f"{f}\t{act}" for f, act in files) == sorted(
            ["//depot/proj/src/b/g0.c\tedit", "//depot/proj/src/d/new.c\tadd", "//depot/proj/src/a/f1.c\tdelete"])
        assert p4("opened").strip() == "" and not (ws / "src/d/new.c").exists() and (ws / "src/a/f1.c").exists()
        assert not (ws / "docs").exists() and not (ws / "src/d").exists()    # no empty directories left behind
        rows = list(csv.DictReader(out.open(), delimiter="\t"))
        assert [(r_["kind"], r_["sha"]) for r_ in rows] == [("base", base[:9]), ("catch-up", large[:9]),
                                                             ("commit", large[:9]), ("shelved", shelved[:9])]
        assert [r_["cl"] for r_ in rows] == [c.split("\t")[0] for c in reversed(changes)]
        assert rows[2]["c_files"] == "36" and rows[2]["dirs"] == "4" and rows[2]["subject"] == "large: add the b and c modules"
        again = run("--repo", str(src), "--base", base, "--depot", "//depot/proj", "--workspace", str(tmp_path / "ws2"),
                    "--client", "proj-ws2", "--port", port, env=env)
        assert again.returncode != 0 and "already has files" in again.stderr
    finally:
        pid = root / "p4d.pid"
        if pid.exists():
            os.kill(int(pid.read_text()), signal.SIGTERM)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && PATH="${LAB:-/media/anoop/ssd_1/Work/tortoise-lab}/bin:$PATH" uv run pytest tests/test_lab_import.py -q`
Expected: FAIL — `2 failed` (`can't open file '…/lab/p4-import.py': [Errno 2] No such file or directory`)

- [ ] **Step 3: Implement**

`lab/p4-import.py`:

```python
#!/usr/bin/env python3
"""Builds a Perforce history from a git project, for testing CodeTortoise on large changes by hand.

Imports the base snapshot, then for each chosen commit one catch-up changelist (everything between the previous
point and the commit's first parent) and the commit itself as one changelist. Commits given to --shelve become pending
changelists, shelved on top of head at that point. Writes a TSV of the changelists
(C files and directories count C/C++ files outside tests). Run by hand, never as a service:
if no server answers at --port and --root is given, it starts p4d in the background and says how to stop it.

  lab/p4-import.py --repo https://github.com/libgit2/libgit2.git --clone $LAB/upstream --base <sha> --end main \\
      --depot //depot/libgit2-big --workspace $LAB/big-ws --client big-ws --exclude tests/resources --out $LAB/big-cls.tsv
  lab/p4-import.py --repo $LAB/upstream --base <sha> --end main --list      # the commits it would pick
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

C_EXT = {".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".inl"}
TEST_DIRS = {"test", "tests", "testing", "unittest", "unittests"}
BATCH = 2000


def die(msg: str) -> None:
    print(f"p4-import: {msg}", file=sys.stderr)
    sys.exit(1)


# --- git -------------------------------------------------------------------------------------------------------------

class Git:
    def __init__(self, repo: str, clone: str | None):
        if re.match(r"^[a-z+]+://|^git@", repo):
            dest = Path(clone or Path.cwd() / posixpath.basename(repo.rstrip("/")).removesuffix(".git"))
            if not dest.exists():
                print(f"cloning {repo} into {dest}")
                subprocess.run(["git", "clone", "-q", "--bare", repo, str(dest)], check=True)
            repo = str(dest)
        self.dir = repo
        self.env = os.environ | {"GIT_LITERAL_PATHSPECS": "1"}

    def __call__(self, *args: str, input: bytes | None = None, env: dict | None = None) -> bytes:
        r = subprocess.run(["git", "-C", self.dir, *args], input=input, capture_output=True, env=env or self.env)
        if r.returncode:
            die(f"git {' '.join(args[:3])}: {r.stderr.decode(errors='replace').strip()}")
        return r.stdout

    def sha(self, rev: str) -> str:
        return self("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()

    def subject(self, sha: str) -> str:
        return self("log", "-1", "--format=%s", sha).decode().strip()

    def first_parent(self, sha: str) -> str:
        return self.sha(f"{sha}^1")

    def chain(self, base: str, end: str) -> list[str]:
        return self("rev-list", "--first-parent", "--reverse", f"{base}..{end}").decode().split()

    def diff(self, a: str, b: str) -> list[Change]:
        """Changes from a to b, renames as a delete and an add."""
        out = self("diff", "--raw", "--no-renames", "-z", "--no-abbrev", a, b).decode(errors="surrogateescape")
        parts = out.split("\0")
        changes = []
        for meta, path in zip(parts[0::2], parts[1::2], strict=False):
            if not meta:
                continue
            old_mode, new_mode, _, _, status = meta.lstrip(":").split()
            changes.append(Change(path, status[0], old_mode, new_mode))
        return changes

    def files(self, rev: str) -> list[Change]:
        out = self("ls-tree", "-r", "-z", "--full-tree", rev).decode(errors="surrogateescape")
        changes = []
        for entry in filter(None, out.split("\0")):
            meta, path = entry.split("\t", 1)
            mode, kind, _ = meta.split()
            if kind == "blob":
                changes.append(Change(path, "A", "000000", mode))
        return changes

    def checkout(self, rev: str, paths: list[str], dest: Path) -> None:
        """Writes rev's version of paths into dest, with their modes and symlinks."""
        if not paths:
            return
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env | {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
            self("read-tree", rev, env=env)
            self("--work-tree", str(dest), "checkout-index", "-f", "-z", "--stdin",
                 input="\0".join(paths).encode(errors="surrogateescape"), env=env)


@dataclass
class Change:
    path: str
    status: str        # A, M, D or T (type change)
    old_mode: str
    new_mode: str


def is_c(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in C_EXT


def is_test(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return bool(TEST_DIRS & set(parts[:-1])) or name.startswith("test_") or bool(re.search(r"_tests?\.\w+$", name))


def c_stats(changes: list[Change]) -> tuple[int, int]:
    """C/C++ files outside tests, and their directories."""
    files = [c.path for c in changes if is_c(c.path) and not is_test(c.path)]
    return len(files), len({posixpath.dirname(f) for f in files})


def excluded(path: str, patterns: list[str]) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") or fnmatch.fnmatch(path, p) for p in patterns)


# --- p4 --------------------------------------------------------------------------------------------------------------

def escape(path: str) -> str:
    return path.replace("%", "%25").replace("@", "%40").replace("#", "%23").replace("*", "%2A")


class P4:
    def __init__(self, port: str, client: str, cwd: Path):
        self.port, self.client, self.cwd = port, client, cwd

    def __call__(self, *args: str, input: str | None = None, check: bool = True) -> str:
        r = subprocess.run(["p4", "-p", self.port, "-c", self.client, *args], input=input, capture_output=True, text=True,
                           cwd=self.cwd)
        if check and (r.returncode or r.stderr.strip() and "no such file" not in r.stderr and "file(s) not" not in r.stderr):
            die(f"p4 {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()}")
        return r.stdout

    def batch(self, args: list[str], paths: list[str]) -> None:
        for i in range(0, len(paths), BATCH):
            self("-x", "-", *args, input="\n".join(paths[i:i + BATCH]) + "\n")


def ensure_server(port: str, root: str | None, password: str) -> int | None:
    """Returns the pid of a p4d this run started, or None when one was already answering. A new server needs a
    password: the first user sets one (and becomes super), as lab/setup.sh does, and logs in."""
    if subprocess.run(["p4", "-p", port, "info"], capture_output=True).returncode == 0:
        return None
    if not root:
        die(f"no Perforce server answers at {port}; pass --root to start one")
    r = Path(root)
    r.mkdir(parents=True, exist_ok=True)
    log = open(r / "p4d.out", "ab")                                       # noqa: SIM115 (kept open for the daemon)
    proc = subprocess.Popen(["p4d", "-r", str(r), "-p", port, "-L", str(r / "log"), "-J", str(r / "journal")],
                            stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    (r / "p4d.pid").write_text(str(proc.pid))
    for _ in range(100):
        if subprocess.run(["p4", "-p", port, "info"], capture_output=True).returncode == 0:
            for cmd, given in ((["passwd"], f"{password}\n{password}\n"), (["login"], f"{password}\n")):
                out = subprocess.run(["p4", "-p", port, *cmd], input=given, capture_output=True, text=True)
                if out.returncode:
                    die(f"p4 {cmd[0]} on the new server: {(out.stderr or out.stdout).strip()}")
            print(f"started p4d (pid {proc.pid}) at {port} under {r}; stop it with: kill {proc.pid}")
            return proc.pid
        if proc.poll() is not None:
            die(f"p4d exited ({proc.returncode}); see {r / 'p4d.out'}")
        time.sleep(0.1)
    die(f"p4d did not answer at {port}")
    return None


def setup(p4: P4, depot: str, ws: Path) -> None:
    depot = depot.rstrip("/").removesuffix("/...")
    if p4("files", "-m1", f"{depot}/...", check=False).strip():
        die(f"{depot}/... already has files; choose a new --depot")
    if ws.exists() and any(ws.iterdir()):
        die(f"workspace {ws} is not empty")
    ws.mkdir(parents=True, exist_ok=True)
    name = depot.split("/")[2]
    if f"Depot {name} " not in p4("depots"):
        p4("depot", "-i", input=p4("depot", "-o", name))
    spec = p4("--field", f"Root={ws}", "--field", f"View={depot}/... //{p4.client}/...",
              "--field", "Options=allwrite clobber nocompress unlocked nomodtime rmdir", "client", "-o", p4.client)
    p4("client", "-i", input=spec)


def open_changes(p4: P4, git: Git, rev: str, changes: list[Change], ws: Path) -> int:
    """Opens changes (git's version at rev) in the default changelist. Returns how many files were opened."""
    local = lambda c: str(ws / c.path)                                    # noqa: E731
    deletes = [c for c in changes if c.status == "D"]
    edits = [c for c in changes if c.status in "MT"]
    adds = [c for c in changes if c.status == "A"]
    p4.batch(["delete"], [escape(local(c)) for c in deletes])
    p4.batch(["edit"], [escape(local(c)) for c in edits])
    for c in edits:
        if c.new_mode == "120000" or c.old_mode == "120000":           # git writes a symlink over the file and back
            Path(local(c)).unlink(missing_ok=True)
    git.checkout(rev, [c.path for c in edits + adds], ws)
    p4.batch(["add", "-f"], [local(c) for c in adds if c.new_mode != "100755"])
    p4.batch(["add", "-f", "-t", "+x"], [local(c) for c in adds if c.new_mode == "100755"])
    for c in edits:                                                       # executable bit or symlink changed
        if c.old_mode == c.new_mode:
            continue
        if c.new_mode == "120000":
            p4("reopen", "-t", "symlink", escape(local(c)))
        elif c.new_mode == "100755":
            p4("reopen", "-t", "text+x" if c.old_mode == "120000" else "+x", escape(local(c)))
        else:
            head = p4("-ztag", "-F", "%headType%", "fstat", escape(local(c))).strip()
            p4("reopen", "-t", "text" if c.old_mode == "120000" else plain(head), escape(local(c)))
    return len(changes)


def plain(filetype: str) -> str:
    """The filetype without the executable modifier: text+x and xtext become text."""
    base, _, mods = {"xtext": "text+x", "xbinary": "binary+x", "kxtext": "text+kx", "cxtext": "text+Cx",
                     "xunicode": "unicode+x", "xutf16": "utf16+x"}.get(filetype, filetype).partition("+")
    mods = mods.replace("x", "")
    return base + (f"+{mods}" if mods else "")


def submit(p4: P4, desc: str) -> str:
    out = p4("-ztag", "submit", "-d", desc)
    m = re.search(r"submittedChange (\d+)", out)
    if not m:
        die(f"submit gave no changelist: {out.strip()}")
    return m.group(1)


def shelve(p4: P4, desc: str) -> str:
    spec = p4("--field", f"Description={desc}", "change", "-o")
    m = re.search(r"Change (\d+) created", p4("change", "-i", input=spec))
    if not m:
        die("could not create a pending changelist")
    cl = m.group(1)
    p4("shelve", "-c", cl)
    p4("revert", "-w", "-c", cl, f"//{p4.client}/...")
    return cl


# --- main ------------------------------------------------------------------------------------------------------------

def pick(git: Git, base: str, end: str, min_files: int, excludes: list[str]) -> list[tuple[str, int, int]]:
    out = []
    for sha in git.chain(base, end):
        changes = [c for c in git.diff(git.first_parent(sha), sha) if not excluded(c.path, excludes)]
        n, dirs = c_stats(changes)
        if n >= min_files:
            out.append((sha, n, dirs))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="git URL or local clone")
    ap.add_argument("--clone", help="where to clone a URL (default: ./<name>)")
    ap.add_argument("--base", required=True, help="commit to import as the starting snapshot")
    ap.add_argument("--end", default="HEAD", help="last commit of the range to pick from (default HEAD)")
    ap.add_argument("--commits", nargs="*", default=None, help="exact commits to import (default: picked by --min-files)")
    ap.add_argument("--min-files", type=int, default=30,
                    help="pick first-parent commits touching this many C/C++ files outside tests")
    ap.add_argument("--shelve", nargs="*", default=[], help="commits to shelve as pending changelists instead of submitting")
    ap.add_argument("--exclude", action="append", default=[], help="path prefix or glob to leave out (repeatable)")
    ap.add_argument("--list", action="store_true", help="print the picked commits (sha, C files, directories, subject) and stop")
    ap.add_argument("--depot", default="//depot/libgit2-big", help="depot path to import into (must be empty)")
    ap.add_argument("--workspace", help="client root (must be empty)")
    ap.add_argument("--client", default="big-ws")
    ap.add_argument("--port", default=os.environ.get("P4PORT", "127.0.0.1:1666"))
    ap.add_argument("--root", help="p4d root, used to start a server if none answers at --port")
    ap.add_argument("--password", default=os.environ.get("OWNER_PASSWD", "TortoiseLab-2026"),
                    help="password set for you on a server this run starts (default as lab/setup.sh)")
    ap.add_argument("--out", default="cls.tsv", help="where to write the changelist table")
    a = ap.parse_args()

    git = Git(a.repo, a.clone)
    base, end = git.sha(a.base), git.sha(a.end)
    chain = git.chain(base, end)
    if a.list:
        for sha, n, dirs in pick(git, base, end, a.min_files, a.exclude):
            print(f"{sha[:9]}\t{n}\t{dirs}\t{git.subject(sha)}")
        return
    if not a.workspace:
        die("--workspace is required to import")
    if a.commits is not None:
        chosen = [git.sha(c) for c in a.commits]
    else:
        chosen = [s for s, _, _ in pick(git, base, end, a.min_files, a.exclude)]
    shelved = {git.sha(c) for c in a.shelve}
    order = {s: i for i, s in enumerate(chain)}
    for s in set(chosen) | shelved:
        if s not in order:
            die(f"{s[:9]} is not a first-parent commit between --base and --end")
    todo = sorted(set(chosen) | shelved, key=order.__getitem__)
    if not todo:
        die("no commits to import; lower --min-files or pass --commits")

    ensure_server(a.port, a.root, a.password)
    ws = Path(a.workspace).resolve()
    p4 = P4(a.port, a.client, Path.cwd())
    setup(p4, a.depot, ws)
    p4.cwd = ws
    keep = lambda cs: [c for c in cs if not excluded(c.path, a.exclude)]  # noqa: E731
    rows = []

    def record(cl: str, kind: str, sha: str, subject: str, changes: list[Change]) -> None:
        n, dirs = c_stats(changes)
        rows.append((cl, kind, sha[:9], subject, n, dirs))
        print(f"CL {cl}\t{kind}\t{sha[:9]}\t{n} C files in {dirs} directories\t{subject}")

    changes = keep(git.files(base))
    open_changes(p4, git, base, changes, ws)
    record(submit(p4, f"import at upstream {base[:9]}"), "base", base, "", changes)
    at = base
    for sha in todo:
        parent = git.first_parent(sha)
        if parent != at and (changes := keep(git.diff(at, parent))):
            open_changes(p4, git, parent, changes, ws)
            record(submit(p4, f"catch-up to {sha[:9]}"), "catch-up", sha, "", changes)
        at = parent
        changes = keep(git.diff(parent, sha))
        if not changes:
            print(f"skipping {sha[:9]}: nothing left after --exclude")
            continue
        subject = git.subject(sha)
        open_changes(p4, git, sha, changes, ws)
        desc = f"{subject} (upstream {sha[:9]})"
        if sha in shelved:
            record(shelve(p4, desc), "shelved", sha, subject, changes)
        else:
            record(submit(p4, desc), "commit", sha, subject, changes)
            at = sha
    with open(a.out, "w") as f:
        f.write("cl\tkind\tsha\tsubject\tc_files\tdirs\n")
        for row in rows:
            f.write("\t".join(str(x).replace("\t", " ") for x in row) + "\n")
    print(f"wrote {len(rows)} changelists to {a.out}")


if __name__ == "__main__":
    main()
```

`lab/build.sh` (replace the whole file):

```
#!/usr/bin/env bash
# Configures and builds the imported libgit2 so compile_commands.json and generated headers exist.
set -euo pipefail
LAB=${LAB:?set LAB}
WS=${WS:-$LAB/ws} BUILD=${BUILD:-$LAB/build}      # WS=$LAB/big-ws BUILD=$LAB/big-build for the large-change import
cmake -S "$WS" -B "$BUILD" -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Debug \
  -DUSE_SSH=OFF -DUSE_HTTPS=OFF -DUSE_AUTH_NTLM=OFF -DUSE_AUTH_NEGOTIATE=OFF -DBUILD_TESTS=ON \
  -DREGEX_BACKEND=builtin -DUSE_BUNDLED_ZLIB=ON > "$BUILD-config.log"
cmake --build "$BUILD" -j "$(nproc)" > "$BUILD.log"
python3 -c "import json;print(len(json.load(open('$BUILD/compile_commands.json'))),'TUs in compile_commands.json')"
```

`lab/README.md`:

````diff
diff --git a/lab/README.md b/lab/README.md
index b3e16a3..7532c87 100644
--- a/lab/README.md
+++ b/lab/README.md
@@ -54,3 +54,44 @@ demand (`p4 print` at the workspace's have revision).
   or state effects).
 - LLM storyboard with qwen3.5-9b: ~35–40 s per call; grounded (all cites valid); surfaced an extra side effect the
   detector marked as covered (`!= GIT_EOL_CRLF` treats `-1` as non-CRLF and skips conversion).
+
+## Large changes: libgit2-big
+
+`lab/p4-import.py` imports libgit2's large merges as exact changelists under a new depot path, for testing the
+overview and cluster boards at size. `//depot/libgit2` and the CLs above are left alone. Run it by hand: if no server
+answers at `--port` and `--root` is given, it starts a `p4d` there in the background and prints how to stop it.
+
+```bash
+source $LAB/env.sh                                  # and `p4 login` if the ticket has expired
+lab/p4-import.py --repo $LAB/upstream --base 1de5a32dd^1 --end main --exclude tests/resources --list
+lab/p4-import.py --repo $LAB/upstream --base 1de5a32dd^1 --end main --exclude tests/resources \
+    --depot //depot/libgit2-big --workspace $LAB/big-ws --client big-ws --shelve d29fe50de --out $LAB/big-cls.tsv
+WS=$LAB/big-ws BUILD=$LAB/big-build lab/build.sh
+```
+
+`--list` prints the first-parent commits after the base that touch at least `--min-files` (30) C/C++ files outside
+tests. Each becomes one changelist ("<subject> (upstream <sha>)"), preceded by a catch-up changelist with everything
+between it and the previous one ("catch-up to <sha>"). `--shelve` makes a commit a pending changelist shelved on top of
+head instead (here #7261). `$LAB/big-cls.tsv` lists every changelist: number, kind, sha, subject, C files and
+directories (outside tests).
+
+For the review, copy `$LAB/tortoise.yaml` to `$LAB/tortoise-big.yaml` and change `client: big-ws`,
+`root: $LAB/big-ws`, `compile_commands: $LAB/big-build/compile_commands.json`, `data_dir: $LAB/big-data` and the port,
+then `$CT index --config $LAB/tortoise-big.yaml` and `$CT review --config $LAB/tortoise-big.yaml <CL>`.
+
+Imported into a fresh server (the CL numbers below; the lab server continues its own numbering) and reviewed
+headless without an LLM, every board has at most 30 nodes:
+
+| CL | Upstream | Changed functions | Files | Boards |
+|---|---|---|---|---|
+| 2 | #6896 vector (`git_vector_free` → `git_vector_dispose` at every caller) | 139 | 65 | 8 clusters |
+| 4 | #6897 hashmap | 240 | 63 | 18 clusters |
+| 6 | merge of main into the ssh branch | — | — | one board, 30 nodes |
+| 8 | #6975 sha256 simplification | 546 | 213 | 26 clusters |
+| 9 | #6994 cmake | 49 | 79 | 3 clusters |
+| 11 | #7117 reftables (new code: 351 new fields) | 387 | 66 | 45 clusters |
+| 13 | #7278 pcre → pcre2 | 247 | 81 | 40 clusters |
+| 15 | #7292 docs update | — | — | one board, 27 nodes |
+| 17 (shelved) | #7261 sha256 | 179 | 85 | 15 clusters |
+
+Each review takes 30–80 s. Facts are "degraded" on the older CLs: the workspace and its compile commands are at head.
````

Make it executable:

```bash
chmod +x lab/p4-import.py
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && PATH="${LAB:-/media/anoop/ssd_1/Work/tortoise-lab}/bin:$PATH" uv run pytest tests/test_lab_import.py -q`
Expected: `2 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `372 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add lab/p4-import.py lab/build.sh lab/README.md backend/tests/test_lab_import.py
git commit -m "feat(lab): import a git project's large commits into Perforce as exact changelists"
```

---

## Finish

- [ ] Run everything: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `372 passed, 1 skipped`), and
  `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test` (expected `Tests  91 passed (91)` and `43 passed`).
- [ ] With the lab binaries on PATH, the import test runs too: `cd backend && PATH="${LAB:-/media/anoop/ssd_1/Work/tortoise-lab}/bin:$PATH" uv run pytest tests/test_lab_import.py -q` (expected `2 passed`).
- [ ] At size, by hand (lab README, "Large changes: libgit2-big"): import libgit2-big, build it, review the #6896 changelist and open the review page. Expected: an overview of 8 clusters, every board at most 30 nodes, "+N callers" and Reset working on a cluster board.
