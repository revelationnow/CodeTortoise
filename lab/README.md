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
