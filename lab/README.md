# CodeTortoise lab: Perforce + Swarm + libgit2

A local stand-in for a real Perforce shop, used to validate CodeTortoise on a medium-sized C codebase.

| Piece | What it is |
|---|---|
| p4d | Helix Core r26.1 in a rootless container, `127.0.0.1:1666` |
| Swarm | `perforce/helix-swarm:2026.3` + Redis, `http://localhost:8081` |
| Codebase | libgit2 `main` @ `36b887915` (~1,190 C files; 726 TUs in `compile_commands.json`, built with gcc) |
| Submitted CLs 2–26 | the next 25 upstream first-parent commits (merged PRs), one CL each |
| Shelved CLs 27–30 | planted side effects with known expected findings (below) |
| LLM | LM Studio, `qwen/qwen3.5-9b` (16k context) on an 8 GB GPU |

## Run

```bash
export LAB=$HOME/tortoise-lab
lab/setup.sh && lab/import.sh && lab/build.sh && lab/plant.sh && lab/swarm.sh
cp lab/tortoise.yaml.template $LAB/tortoise.yaml   # then substitute $LAB and the owner
source $LAB/env.sh
$CT index  --config $LAB/tortoise.yaml
$CT review --config $LAB/tortoise.yaml 28 29
$CT serve  --config $LAB/tortoise.yaml
```

## Planted CLs and what CodeTortoise must report

| CL | Change | Expected |
|---|---|---|
| 27 | `output_eol` also returns `GIT_EOL_NATIVE` | **no finding**: on Linux `GIT_EOL_NATIVE == GIT_EOL_LF`, callers already handle it |
| 30 | `output_eol` returns `-1` when attributes are not loaded | **high contract**: `check_safecrlf` compares only `== GIT_EOL_LF` / `== GIT_EOL_CRLF` (crlf.c:166, :186); `!= GIT_EOL_CRLF` at :265 covered |
| 28 | `git_repository_head_detached()` resets `configmap_cache` through `intptr_t *cache = repo->configmap_cache` | **high field mutation** with readers `git_repository__configmap_lookup*` (precise via follow-up TU) |
| 29 (stacked on 28) | new `git_repository::head_detached_cache` written through `int *detached` | **high header fan-out** (273 TUs, 6 layers) + **medium field mutation** |

## Review board check

After `$CT review … 30` and `$CT review … 28 29`, the `board` stage is `ok` and the board (`GET /api/reviews/<id>/board`,
or the review page in a browser) shows:

| Review | Flows | Annotations |
|---|---|---|
| 30 | 1 contract flow: `check_safecrlf → output_eol ⟶ -1 unhandled` | crlf.c:133 new return value `-1` (on `output_eol`); crlf.c:166 and :186 warn (`checks GIT_EOL_LF (==2)` / `GIT_EOL_CRLF (==1)` — does not handle -1); crlf.c:265 ok (`!=1` covers -1) |
| 28+29 | 2 state flows: `git_repository_head_detached → git_repository::configmap_cache → git_repository__configmap_lookup` and `… → git_repository__configmap_lookup_cache_clear` | repository.c:3058 and :3071 (writes through aliases `cache`, `detached`); config_cache.c:114, :128, :139 warn (reads and writes `configmap_cache`); repository.h:172 warn (new writer, readers); repository.h:165 info (`head_detached_cache`: no readers in the parsed code) |

No test function appears as a flow entry or as a board node; every function node has a depot path, so its code opens on
demand (`p4 print` at the workspace's have revision).

## Results at the time of writing

- Index: 1,190 files in 4.3 s. Headless review without LLM: 3–20 s (CL 20, 22 changed functions, 223 TU parses: ~20 s).
- All planted effects detected with the expected severities; CL 27 correctly silent.
- Real upstream CLs: CL 20 (index extensions) → 8 findings (header fan-out, signature change with 4 callers, vector field
  mutations, new-function summaries); CL 23/24 (overflow fix, CVE escaping fix) → no findings (local changes, no contract
  or state effects).
- LLM storyboard with qwen3.5-9b: ~35–40 s per call; grounded (all cites valid); surfaced an extra side effect the
  detector marked as covered (`!= GIT_EOL_CRLF` treats `-1` as non-CRLF and skips conversion).

## Large changes: libgit2-big

`lab/p4-import.py` imports libgit2's large merges as exact changelists under a new depot path, for testing the
overview and cluster boards at size. `//depot/libgit2` and the CLs above are left alone. Run it by hand: if no server
answers at `--port` and `--root` is given, it starts a `p4d` there in the background and prints how to stop it.

```bash
source $LAB/env.sh                                  # and `p4 login` if the ticket has expired
lab/p4-import.py --repo $LAB/upstream --base 1de5a32dd^1 --end main --exclude tests/resources --list
lab/p4-import.py --repo $LAB/upstream --base 1de5a32dd^1 --end main --exclude tests/resources \
    --depot //depot/libgit2-big --workspace $LAB/big-ws --client big-ws --shelve d29fe50de --out $LAB/big-cls.tsv
WS=$LAB/big-ws BUILD=$LAB/big-build lab/build.sh
```

`--list` prints the first-parent commits after the base that touch at least `--min-files` (30) C/C++ files outside
tests. Each becomes one changelist ("<subject> (upstream <sha>)"), preceded by a catch-up changelist with everything
between it and the previous one ("catch-up to <sha>"). `--shelve` makes a commit a pending changelist shelved on top of
head instead (here #7261). `$LAB/big-cls.tsv` lists every changelist: number, kind, sha, subject, C files and
directories (outside tests).

For the review, copy `$LAB/tortoise.yaml` to `$LAB/tortoise-big.yaml` and change `client: big-ws`,
`root: $LAB/big-ws`, `compile_commands: $LAB/big-build/compile_commands.json`, `data_dir: $LAB/big-data` and the port,
then `$CT index --config $LAB/tortoise-big.yaml` and `$CT review --config $LAB/tortoise-big.yaml <CL>`.

Imported into a fresh server (the CL numbers below; the lab server continues its own numbering) and reviewed
headless without an LLM, every board has at most 30 nodes:

| CL | Upstream | Changed functions | Files | Boards |
|---|---|---|---|---|
| 2 | #6896 vector (`git_vector_free` → `git_vector_dispose` at every caller) | 139 | 65 | 8 clusters |
| 4 | #6897 hashmap | 240 | 63 | 18 clusters |
| 6 | merge of main into the ssh branch | — | — | one board, 30 nodes |
| 8 | #6975 sha256 simplification | 546 | 213 | 26 clusters |
| 9 | #6994 cmake | 49 | 79 | 3 clusters |
| 11 | #7117 reftables (new code: 351 new fields) | 387 | 66 | 45 clusters |
| 13 | #7278 pcre → pcre2 | 247 | 81 | 40 clusters |
| 15 | #7292 docs update | — | — | one board, 27 nodes |
| 17 (shelved) | #7261 sha256 | 179 | 85 | 15 clusters |

Each review takes 30–80 s. Facts are "degraded" on the older CLs: the workspace and its compile commands are at head.

### Change stories

A review opens on its change stories (spec `docs/superpowers/specs/2026-10-04-change-stories-design.md`): at most 15
per review, each story graph at most 12 nodes. The second and third changes below come from a second import, kept small
so its workspace and compile commands sit right after them (`--root` starts a `p4d` on a new port, here 1668):

```bash
lab/p4-import.py --repo $LAB/upstream --base 5ead0bdfb^1 --commits 5ead0bdfb d3b3049a6 --exclude tests/resources \
    --port 127.0.0.1:1668 --root $LAB/big2-p4root --depot //depot/libgit2-big --workspace $LAB/big2-ws \
    --client big2-ws --out $LAB/big2-cls.tsv
WS=$LAB/big2-ws BUILD=$LAB/big2-build lab/build.sh
```

`$LAB/tortoise-big2.yaml` is `tortoise-big.yaml` with `p4port: 127.0.0.1:1668`, `client: big2-ws`, its own `root`,
`compile_commands`, `data_dir` and port. Reviewed headless without an LLM:

| Change | Stories | What the list shows |
|---|---|---|
| #6896 vector (libgit2-big CL 2) | 4 | 1 behaviour story (what `git_vector_free` → `git_vector_dispose` changes: `filesystem_iterator_clear` and 4 more see new values), Other changes in `src/util` (4 functions), and two repeated edits: `git_vector_free` → `git_vector_dispose` at 152 sites in 52 files (47 in tests), `git_vector_free_deep` → `git_vector_dispose_deep` at 28 sites in 19 files. The summary: 180 of 187 changed lines are 2 repeated edits |
| #6897 hashmap (big2 CL 2) | 14 | 8 behaviour stories (the first joins 53 functions), 4 Other stories (56 functions), 1 repeated edit (`git__mwindow_mutex` → `git_mwindow__mutex`, 23 sites) and Tests (37 test functions) |
| #7278 pcre → pcre2 (big2 CL 4) | 15 | 247 changed functions with no flow, in 15 Other stories under `deps/pcre`, `deps/pcre2` and `src/util`: a vendored library swapped, which the stories don't yet tell as one |

No story title or summary shows an absolute path.
