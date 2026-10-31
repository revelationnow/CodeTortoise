# One Server, Many Workspaces — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `codetortoise serve` hosts reviews for any number of workspaces on one or more Perforce servers, with workspaces added in the UI, sign-in per Perforce server and owner rights per workspace.

**Architecture:** A new `Registry` (`backend/codetortoise/workspaces.py`) holds every workspace: its row in the `workspaces` table, its effective configuration and its bundle (today's `Services`, built by `build_services` with a shared store, ledger, LLM clients and AI pool, a folder of its own and a key scope for its store entries) plus a job queue. The web app takes the registry instead of one bundle; every review path resolves the review's workspace and the session's sign-in on that workspace's server (`Access`), and owner checks compare that sign-in with the workspace's `p4user`. The React app reads "who am I" from the review (`viewer`) inside a review and from `/api/me` (sign-ins per server, owned workspace ids) elsewhere; a Workspaces page adds, edits and checks workspaces.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, pytest, ruff; React 19 + TypeScript 5.9, react-router-dom 7, Vite 8, vitest 5 (node environment, pure `src/**/*.test.ts` only), Playwright.

**Spec:** `docs/superpowers/specs/2026-10-31-multi-workspace-server-design.md` (project 1 of 3). Read it before any task: it is the authority; this plan is its argument.

## Global Constraints

- The repository is public. Use generic names only (`fw`, `dsp`, `sensor`, `b`, `second`, `amy`, `bob`, `carol`, `mallory`, `owner`, `demo`). Never put the owner's proprietary identifiers (function or field names, toolchain or target names, build file names or paths from the owner's material) in code, tests, docs or commit messages.
- No absolute local paths in committed files (made-up paths like `/work/sensor` in tests are fine).
- Commit with `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`; every message ends with these two lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH`
- Never stage, read, move or delete the untracked `frontend/e2e/strong-review.txt`. Stage files by name (`git add <paths>`), never `git add -A` or `git add .`.
- Never a bare `git stash`, never `git clean -fdx`, never `--force`. Never push.
- Backend commands run from `backend/`: `.venv/bin/python -m pytest …`, `.venv/bin/ruff check codetortoise tests`. Never `uv`.
- Frontend commands run from `frontend/` only: `npx vitest run`, `npx tsc --noEmit`, `npx tsc -p e2e --noEmit`, `npm run build`.
- Playwright: `npm run build` first; then from `frontend/`: `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test <spec> --reporter=line; rm -rf ../.pwtmp`. Kill stray servers by PID only (never `pkill -f`).
- Scratch files go in `$CLAUDE_JOB_DIR/tmp` when that variable is set, never in `/tmp`.
- Never print `TORTOISE_LLM_KEY` or `TORTOISE_STRONG_KEY`.
- Match the surrounding code: its comment density, docstrings that cite the spec as `spec 2026-10-31 §N` (or `§N` inside a file that already names the spec), naming and idiom. AI text is never hidden in the UI; only its labels may shrink.
- Exact values from the spec, verbatim: a workspace name is 1–40 characters with no `/`; a workspace's Perforce server is its `p4port` as written, or `local`; the 401 body for a review on an unsigned server is `{"detail": "sign in required", "server": "<p4port>"}`; an edit while the workspace is busy is refused with 409 `"a review is running in this workspace; try again when it finishes"`; the seed is refused with 409 `"set in tortoise.yaml"`; the review page prompt reads `Sign in to <server> to open this review`; the account menu lines read `<server> as <user>` and `Sign in to another server`.

## Review Focus

The spec's own test list (§13) is covered task by task. These five input classes are implied by the spec but not named in its tests, and are the most likely to bite someone using the software; each has a test in the task that owns the code:

1. **The same user name on two Perforce servers.** Signed in to `local` as `owner` and to `second:1666` as `mallory`, the session must get no owner rights on a workspace of `second:1666` owned by `owner` — rights follow the sign-in on the workspace's own server, never the name. (Task 5: `test_owner_rights_follow_the_sign_in_on_the_workspaces_own_server`.)
2. **A deep link to a review on a server the session isn't signed in to.** Opening `/r/<id>/cl/102` (a CL's page) signed in elsewhere shows the sign-in prompt in place; after signing in, the same address (the CL's page) opens, not the Reviews page. (Task 8 implements the in-place prompt; Task 10's e2e `a link to a review on the other server signs in from its prompt and opens where it pointed`.)
3. **Two workspaces whose toolchains choose different libclang libraries.** One process can load only one libclang; the second workspace must still prepare and become ready, its library described from a worker process. (Task 3: `test_a_toolchain_that_picks_another_library_than_the_process_has_still_prepares`.)
4. **The first start on a single-workspace data folder (the lab).** Existing reviews open under the seed, the owner's shared-sink marks and the flags libclang rejected carry over to the seed, a libclang installed by `fetch-libclang` into the data folder is still found from the seed's new toolchain folder, and old sign-ins end. (Task 4: `test_the_first_start_after_the_upgrade_keeps_what_the_single_workspace_server_had`; Task 5: `test_sign_ins_from_before_per_server_sign_in_end`.)
5. **A root given in another spelling, and a workspace removed then added again.** `/w/fw/`, `/w/x/../fw` and a symlink to `/w/fw` are the same root (409); a workspace added after another was removed gets a new id, an empty folder and none of the removed one's store entries. (Task 4: `test_a_root_in_another_spelling_is_the_same_root_and_a_removed_workspace_leaves_nothing_behind`.)

## File Structure

Backend (`backend/codetortoise/`):
- `config.py` — modify: optional `workspace`, `workspace.name`, `seed_name`, `valid_name`, `parse_settings`, `effective_config`, `_resolve_paths` (Task 1).
- `store.py` — modify: `workspaces` table and methods, `reviews.workspace_id`, `kv_delete_scope` (Task 2); `session_logins` and the session methods (Task 5).
- `services.py` — modify: `build_services(..., store=, ledger=, home=, scope=)`, `Services.scope`, `strip_flags_key` (Task 3).
- `toolchain/toolchain.py`, `toolchain/libclang.py`, `vcs/p4runner.py`, `sinks.py` (`marks_key`), `pipeline.py` — modify (Task 3).
- `workspaces.py` — create: `Workspace`, `Registry`, `Conflict`, `Invalid`, `server_of`, `scope_of`, `LOCAL` (Task 4).
- `web/app.py` — modify: `create_app(reg, authenticate)`, sign-in per server, `Access`, moved workspace endpoints (Task 5), workspace management endpoints (Task 6).
- `cli.py` — modify: `serve` with the registry, `--workspace` (Task 7).

Backend tests (`backend/tests/`): `test_config.py`, `test_store.py` (modify); `test_bundle.py`, `test_workspaces.py`, `test_signin.py`, `test_workspace_api.py` (create); `helpers.py`, `test_web.py`, `test_ondemand.py`, `test_tortoise.py`, `test_large_change.py`, `test_p4source.py`, `test_sinks.py`, `test_cli.py` (modify).

Frontend (`frontend/src/`):
- `api.ts` (+ `api.test.ts`) — modify (Task 8; Task 9 adds the workspace calls). `viewer.ts` (+ `viewer.test.ts`) — create (Task 8). `lib/signin.ts` (+ test) — create (Task 8). `lib/workspaceForm.ts` (+ test) — create (Task 9). `lib/reviewFilter.ts` (+ test) — modify (Task 8: "Mine" per server; Task 9: workspace chips and New review's order). `board/prefs.ts` — modify (Task 9).
- `components/SignInForm.tsx` — create (Task 8). `pages/Login.tsx`, `App.tsx`, `pages/Health.tsx`, `pages/Reviews.tsx`, `workspace/useReview.ts`, `workspace/Workspace.tsx`, `components/SinkMark.tsx`, `components/Comments.tsx`, `workspace/FindingBody.tsx`, `workspace/ClPage.tsx`, `workspace/ReviewMenu.tsx`, `styles.css`, `workspace/workspace.css` — modify (Task 8). `pages/Workspaces.tsx` — create; `pages/Reviews.tsx`, `App.tsx`, `styles.css` — modify (Task 9).

End to end (`frontend/e2e/`): `landing.spec.ts`, `workspace-sinks.spec.ts`, `workspace-tier1.spec.ts` — modify: the moved endpoints (Task 8); `landing.spec.ts` — modify: the phone menu's Workspaces link (Task 9); `serve-multi.sh`, `multi-workspace.spec.ts` — create, `helpers.ts`, `../playwright.config.ts` — modify (Task 10).

Docs: `README.md` (Task 11).

## Decisions this plan makes where the spec is silent

- A request that names no server (`POST /api/login` without `server`) or no workspace (`POST /api/reviews` without `workspace_id`) is accepted when the server has exactly one; otherwise 422. Today's clients and tests keep working on a server of one workspace.
- `GET /api/reviews/{id}`'s `workspace` and each review row's `workspace` are `{id, name, server}` (the server is what the UI needs for "Mine" and the sign-in prompt).
- A review with no `workspace_id` (made before workspaces) belongs to the seed; startup also writes the seed's id into such rows.
- The seed's `p4_bin` and every UI workspace's `p4_bin` are the seed's `workspace.p4_bin` (else `p4`): one Perforce binary per host.
- Seed rows keep `settings` empty: the seed's toolchain, targets and analysis come from the file. A seed row whose `workspace:` section has since been removed from the file is served from its row, as a workspace "stored by an earlier run", and is no longer read-only.
- Store-entry keys carry the scope `ws<id>`: `layers:v<N>:ws<id>:<generation>`, `strip_flags:ws<id>`, `sink_marks:ws<id>`. A bundle built on its own (tests) keeps today's keys (root-keyed, and the one `sink_marks`).
- Ids of the `workspaces` table never repeat (`AUTOINCREMENT`); removing a workspace deletes its folder and its store entries.
- Adding and editing build the bundle inside the request, so the answer carries the checks (§8); startup builds in the background (§6). A bundle's first index build is queued when its index is empty, whatever its checks say (as `serve` does today).
- Shared-sink rules (`GET /api/workspaces/{id}/sinks`) are owner-only, per the spec's access table (today any signed-in user could read them).
- The add form has a "Version control" choice (Perforce or Git): the spec's form omits it, but git workspaces are what dev mode and the e2e fixture use.
- On a server whose reviews all come from one workspace, rows don't repeat its name and no workspace chips show; the review page always shows the workspace's name beside the title (hidden on phones, like the progress line).
- Inside a review, "who am I" is `viewer` from `GET /api/reviews/{id}` (spec §8). `swarm_ready` leaves `/api/me`: nothing in the UI reads it.
- The spec's "⋯ menu" with a line per sign-in (§9) is the top bar's account menu, opened from the signed-in name: the review header's `⋯` menu belongs to one review, and sign-ins are needed on every page.
- A request that reaches a workspace still being built right after startup waits for it (up to 120 s) instead of being refused as not ready: the e2e servers and a user's first click both come seconds after start.
- A workspace's Health page has a **Recheck** button that runs its checks again (§11's "press Recheck").
- The sign-in form's button waits for the list of servers, so a sign-in never goes out without the server the picker shows.
- In the UI's types `ReviewRow.workspace` is optional: the answer to `POST /api/reviews` is a review row without it.
- The Workspaces page lists what `GET /api/workspaces` gives any signed-in session (the workspaces on its servers); only owners get the top bar's link and the Add, Edit, Remove, Rebuild and Health tools.

---

### Task 1: Configuration — the seed and each workspace's effective configuration

**Files:**
- Modify: `backend/codetortoise/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `WorkspaceConfig.name: str | None = None`; `Config.workspace: WorkspaceConfig | None = None`.
  - `SETTINGS_KEYS = ("toolchain", "targets", "analysis")`
  - `valid_name(name: str) -> bool`
  - `seed_name(cfg: Config) -> str` (needs `cfg.workspace`)
  - `parse_settings(text: str | None) -> dict` (raises `ConfigError`)
  - `effective_config(base: Config, row: Mapping[str, Any]) -> Config` (raises `ConfigError`). `row` has the `workspaces` table's columns: `name, vcs, p4port, client, p4user, root, compile_commands` (JSON text: `"auto"`, a path, or a list of paths), `build_root, swarm_url, settings` (YAML text).

- [ ] **Step 1: Write the failing tests**

Replace the imports at the top of `backend/tests/test_config.py` (today `import pytest` and `from codetortoise.config import ConfigError, load_config`) with:

```python
import json
from pathlib import Path

import pytest

from codetortoise.config import ConfigError, effective_config, load_config, parse_settings, seed_name, valid_name
```

and append:

```python
def test_a_file_without_a_workspace_holds_the_server_settings_alone(tmp_path):
    cfg = load_config(write(tmp_path, "server:\n  port: 9000\nauth:\n  mode: dev\n"))
    assert cfg.workspace is None and cfg.server.port == 9000
    assert cfg.server.data_dir == (tmp_path / ".tortoise").resolve()


def test_the_seed_is_named_by_workspace_name_else_its_client_else_its_root_folder(tmp_path):
    named = load_config(write(tmp_path, """
owner: amy
workspace: {name: firmware, vcs: p4, p4port: "p4:1666", client: amy-ws, root: ws, compile_commands: auto}
"""))
    assert seed_name(named) == "firmware"
    by_client = load_config(write(tmp_path, """
owner: amy
workspace: {vcs: p4, p4port: "p4:1666", client: amy-ws, root: ws, compile_commands: auto}
"""))
    assert seed_name(by_client) == "amy-ws"
    by_folder = load_config(write(tmp_path, """
owner: amy
workspace: {vcs: git, root: projects/fw, compile_commands: auto}
"""))
    assert seed_name(by_folder) == "fw"


def test_names_are_1_to_40_characters_without_a_slash():
    assert valid_name("fw") and valid_name("x" * 40) and valid_name("dsp tools")
    assert not valid_name("") and not valid_name("x" * 41) and not valid_name("a/b")


ROW = {"name": "sensor", "vcs": "p4", "p4port": "ssl:p4b:1666", "client": "amy-sensor", "p4user": "amy",
       "root": "/work/sensor", "compile_commands": json.dumps("build/compile_commands.json"), "build_root": None,
       "swarm_url": "https://swarm.example.com", "settings": ""}


def test_a_workspace_takes_server_llm_and_auth_from_the_file_and_overlays_analysis(tmp_path):
    base = load_config(write(tmp_path, """
server: {port: 9000}
llm: {model: big}
auth: {mode: dev}
analysis: {workers: 2, sink_threshold: 20}
"""))
    cfg = effective_config(base, {**ROW, "settings": "analysis: {sink_threshold: 5}\n"
                                                     "toolchain: {clang: tools/clang}\n"
                                                     "targets: [{match: 'dsp/**', name: dsp}]\n"})
    assert (cfg.server.port, cfg.llm.model, cfg.auth.mode) == (9000, "big", "dev")
    assert (cfg.analysis.workers, cfg.analysis.sink_threshold) == (2, 5)
    assert (cfg.owner, cfg.workspace.name, cfg.workspace.client) == ("amy", "sensor", "amy-sensor")
    assert cfg.workspace.compile_commands == Path("/work/sensor/build/compile_commands.json")   # relative to its root
    assert cfg.toolchain.clang == "/work/sensor/tools/clang" and cfg.targets[0].name == "dsp"
    assert cfg.swarm.url == "https://swarm.example.com"
    assert base.analysis.sink_threshold == 20                       # the file's own settings are untouched


def test_workspace_settings_take_toolchain_targets_and_analysis_only():
    assert parse_settings("") == {} and parse_settings(None) == {}
    with pytest.raises(ConfigError, match="server"):
        parse_settings("server: {port: 1}")
    with pytest.raises(ConfigError, match="not YAML"):
        parse_settings("toolchain: [")
    with pytest.raises(ConfigError, match="mapping"):
        parse_settings("- a")


def test_a_bad_value_in_a_workspaces_settings_is_a_config_error(tmp_path):
    base = load_config(write(tmp_path, "auth: {mode: dev}\n"))
    with pytest.raises(ConfigError):
        effective_config(base, {**ROW, "settings": "analysis: {workers: many}"})
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py -q`
Expected: collection error `ImportError: cannot import name 'effective_config' from 'codetortoise.config'`.

- [ ] **Step 3: Implement**

In `backend/codetortoise/config.py`:

Imports become:

```python
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
```

`WorkspaceConfig` gains a first field:

```python
class WorkspaceConfig(BaseModel):
    name: str | None = None          # what the UI calls it (spec 2026-10-31 §4); default: its client's, or its root folder's
    vcs: Literal["p4", "git"] = "p4"
```

(the other fields unchanged). In `Config`, the `owner` comment and `workspace` field become:

```python
    owner: str = ""                  # the seed workspace's owner; defaults to P4USER (P4CONFIG file, then environment)
    server: ServerConfig = Field(default_factory=ServerConfig)
    workspace: WorkspaceConfig | None = None   # the seed workspace (spec 2026-10-31 §4); none: the stored ones alone
```

Replace `load_config` with this version (the workspace part only runs when there is a workspace; path resolution moves to `_resolve_paths`):

```python
def load_config(path: Path, env: Mapping[str, str] | None = None) -> Config:
    """Read tortoise.yaml. Missing `owner`, `workspace.p4port` and `workspace.client` come from Perforce's own settings:
    the P4CONFIG file found from the workspace root, then P4USER/P4PORT/P4CLIENT in the environment (`env`). A file
    with no `workspace` section holds the server-wide settings alone (spec 2026-10-31 §4)."""
    from codetortoise.vcs.p4settings import p4_settings
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
    try:
        cfg = Config.model_validate(raw)
    except Exception as e:  # pydantic.ValidationError
        raise ConfigError(str(e)) from e
    base = path.parent
    ws = cfg.workspace
    if ws is not None:
        ws.root = (base / ws.root).resolve() if not ws.root.is_absolute() else ws.root
        p4 = p4_settings(ws.root, env)
        wanted = [("owner", cfg, "owner", "P4USER")]
        if ws.vcs == "p4":
            wanted += [("workspace.p4port", ws, "p4port", "P4PORT"), ("workspace.client", ws, "client", "P4CLIENT")]
        for label, obj, attr, var in wanted:
            if getattr(obj, attr):
                ws.p4_sources[attr] = "tortoise.yaml"
                continue
            value = p4.get(var)
            if not value:
                where = f"the P4CONFIG file {p4.file}" if p4.file else "no P4CONFIG file was found"
                raise ConfigError(f"{label} is not set: not in tortoise.yaml, {where}, and {var} is not in the environment")
            setattr(obj, attr, value)
            ws.p4_sources[attr] = p4.source(var) or ""
        _resolve_paths(cfg, base)
    if not cfg.server.data_dir.is_absolute():
        cfg.server.data_dir = (base / cfg.server.data_dir).resolve()
    srv = cfg.server
    if (srv.tls_cert is None) != (srv.tls_key is None):
        raise ConfigError("server.tls_cert and server.tls_key must be set together")
    if srv.tls_cert is not None and srv.tls_key is not None:
        srv.tls_cert = srv.tls_cert if srv.tls_cert.is_absolute() else (base / srv.tls_cert).resolve()
        srv.tls_key = srv.tls_key if srv.tls_key.is_absolute() else (base / srv.tls_key).resolve()
        for name, f in (("tls_cert", srv.tls_cert), ("tls_key", srv.tls_key)):
            if not f.is_file():
                raise ConfigError(f"server.{name}: no such file: {f}")
    return cfg


def _resolve_paths(cfg: Config, base: Path) -> None:
    """The workspace's and the toolchain's relative paths, made absolute against `base` (tortoise.yaml's folder, or a
    workspace's root); a program or library given by its bare name stays a name."""
    ws = cfg.workspace

    def rel(p: Path) -> Path:
        return p if p.is_absolute() else (base / p).resolve()
    if isinstance(ws.compile_commands, list):
        ws.compile_commands = [rel(p) for p in ws.compile_commands]
    elif ws.compile_commands != "auto":
        ws.compile_commands = rel(ws.compile_commands)
    ws.build_root = rel(ws.build_root) if ws.build_root is not None else None

    def rel_name(v: str | None) -> str | None:       # a program or library path; a bare name stays a name
        return str(rel(Path(v))) if v and ("/" in v or v.startswith(".")) else v
    tc = cfg.toolchain
    tc.libclang, tc.clang = rel_name(tc.libclang), rel_name(tc.clang)
    tc.search_paths = [str(rel(Path(p))) for p in tc.search_paths]
    for o in tc.overrides:
        o.compile_commands = rel(o.compile_commands) if o.compile_commands is not None else None
        o.libclang, o.clang = rel_name(o.libclang), rel_name(o.clang)


SETTINGS_KEYS = ("toolchain", "targets", "analysis")


def valid_name(name: str) -> bool:
    """A workspace's name (spec 2026-10-31 §5): 1–40 characters, no /."""
    return 1 <= len(name) <= 40 and "/" not in name


def seed_name(cfg: Config) -> str:
    """The seed workspace's name (spec 2026-10-31 §4): `workspace.name`, else its client's, else its root folder's."""
    ws = cfg.workspace
    return ws.name or ws.client or ws.root.name


def parse_settings(text: str | None) -> dict:
    """A workspace's Advanced settings: tortoise.yaml's `toolchain`, `targets` and `analysis` keys, as YAML text."""
    try:
        got = yaml.safe_load(text or "") or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"settings: not YAML: {e}") from e
    if not isinstance(got, dict):
        raise ConfigError("settings: a mapping of toolchain, targets and analysis")
    extra = sorted(str(k) for k in got if k not in SETTINGS_KEYS)
    if extra:
        raise ConfigError(f"settings: only toolchain, targets and analysis belong here, not {', '.join(extra)}")
    return got


def effective_config(base: Config, row: Mapping[str, Any]) -> Config:
    """A stored workspace's configuration (spec 2026-10-31 §4): `server`, `llm` and `auth` from tortoise.yaml; `analysis`
    the file's, overlaid with the workspace's own; `workspace`, `toolchain`, `targets` and `swarm` the workspace's.
    Relative paths in it are relative to the workspace's root."""
    s = parse_settings(row.get("settings"))
    raw = {"owner": row["p4user"], "server": base.server.model_dump(), "llm": base.llm.model_dump(),
           "auth": base.auth.model_dump(), "analysis": {**base.analysis.model_dump(), **(s.get("analysis") or {})},
           "workspace": {"name": row["name"], "vcs": row["vcs"], "p4port": row["p4port"], "client": row["client"],
                         "root": row["root"], "compile_commands": json.loads(row["compile_commands"]),
                         "build_root": row["build_root"],
                         "p4_bin": base.workspace.p4_bin if base.workspace is not None else "p4"},
           "toolchain": s.get("toolchain") or {}, "targets": s.get("targets") or [], "swarm": {"url": row["swarm_url"]}}
    try:
        cfg = Config.model_validate(raw)
    except Exception as e:  # pydantic.ValidationError
        raise ConfigError(str(e)) from e
    _resolve_paths(cfg, Path(row["root"]))
    return cfg
```

- [ ] **Step 4: Run the config tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py -q`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q -x 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass (nothing else reads a missing workspace yet); ruff clean.

- [ ] **Step 5: Commit**

```bash
cd backend
git add codetortoise/config.py tests/test_config.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(config): a workspace section is optional and names the seed; a stored workspace's effective configuration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: Store — workspaces, and the workspace a review belongs to

**Files:**
- Modify: `backend/codetortoise/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (all on `Store`):
  - `WORKSPACE_FIELDS = ("name", "vcs", "p4port", "client", "p4user", "root", "compile_commands", "build_root", "swarm_url", "settings")` (module level)
  - `add_workspace(fields: dict, source: str, created_by: str) -> int` — raises `sqlite3.IntegrityError` for a taken name or root
  - `update_workspace(wid: int, fields: dict) -> None` — same error
  - `delete_workspace(wid: int) -> None`
  - `get_workspace(wid: int) -> dict | None`; `list_workspaces() -> list[dict]` (by name); `seed_workspace() -> dict | None` (`source = 'config'`)
  - `create_review(title, created_by, cls, workspace_id: int | None = None) -> int`; review rows gain `workspace_id`
  - `adopt_reviews(wid: int) -> int` (rows with no workspace get `wid`; returns how many)
  - `review_count(wid: int) -> int`
  - `kv_delete_scope(scope: str) -> None` (deletes keys equal to `…:<scope>` or containing `:<scope>:`)

- [ ] **Step 1: Write the failing tests**

Add `import sqlite3` as the first line of `backend/tests/test_store.py`, above `from datetime import UTC, datetime, timedelta` (standard-library imports, sorted), and append:

```python
WS = {"name": "fw", "vcs": "git", "p4port": None, "client": None, "p4user": "amy", "root": "/w/fw",
      "compile_commands": '"auto"', "build_root": None, "swarm_url": None, "settings": ""}


def test_workspaces_are_stored_with_unique_names_and_roots_and_ids_never_repeat(store):
    a = store.add_workspace(WS, "config", "amy")
    b = store.add_workspace({**WS, "name": "dsp", "root": "/w/dsp"}, "ui", "amy")
    assert [w["name"] for w in store.list_workspaces()] == ["dsp", "fw"]
    assert store.get_workspace(a)["source"] == "config" and store.seed_workspace()["id"] == a
    assert store.get_workspace(b)["created_by"] == "amy"
    with pytest.raises(sqlite3.IntegrityError):
        store.add_workspace({**WS, "root": "/w/other"}, "ui", "amy")             # the name is taken
    with pytest.raises(sqlite3.IntegrityError):
        store.add_workspace({**WS, "name": "other"}, "ui", "amy")                # the root is taken
    store.update_workspace(b, {**WS, "name": "dsp2", "root": "/w/dsp"})
    assert store.get_workspace(b)["name"] == "dsp2"
    store.delete_workspace(b)
    assert store.get_workspace(b) is None
    assert store.add_workspace({**WS, "name": "new", "root": "/w/new"}, "ui", "amy") > b


def test_reviews_belong_to_a_workspace_and_older_ones_are_adopted(store):
    wid = store.add_workspace(WS, "config", "amy")
    old = store.create_review("t", "amy", [1])                                  # made before workspaces
    new = store.create_review("t", "amy", [2], workspace_id=wid)
    assert store.get_review(old)["workspace_id"] is None and store.get_review(new)["workspace_id"] == wid
    assert store.adopt_reviews(wid) == 1 and store.get_review(old)["workspace_id"] == wid
    assert store.adopt_reviews(wid) == 0 and store.review_count(wid) == 2


def test_a_database_made_before_workspaces_gets_the_column(tmp_path):
    db = sqlite3.connect(tmp_path / "old.db")
    db.execute("CREATE TABLE reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_by TEXT, "
               "created_at TEXT, status TEXT, risk TEXT)")
    db.execute("INSERT INTO reviews(title, created_by, status) VALUES('t', 'amy', 'done')")
    db.commit()
    db.close()
    store = Store(tmp_path / "old.db")
    assert store.get_review(1)["workspace_id"] is None


def test_a_workspaces_store_entries_go_with_it(store):
    keys = ["strip_flags:ws1", "sink_marks:ws1", "layers:v3:ws1:4", "sink_marks:ws12", "sink_marks", "strip_flags:/w/ws1"]
    for key in keys:
        store.kv_put(key, [1])
    store.kv_delete_scope("ws1")
    assert [k for k in keys if store.kv_get(k) is not None] == ["sink_marks:ws12", "sink_marks", "strip_flags:/w/ws1"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_store.py -q`
Expected: FAIL with `AttributeError: 'Store' object has no attribute 'add_workspace'` (and `create_review() got an unexpected keyword argument 'workspace_id'`).

- [ ] **Step 3: Implement**

In `backend/codetortoise/store.py`, the `reviews` line of `_SCHEMA` gains the column, and a `workspaces` table joins the schema (after `reviews`):

```python
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_by TEXT,
  created_at TEXT, status TEXT, risk TEXT, workspace_id INTEGER);
CREATE TABLE IF NOT EXISTS workspaces(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
  vcs TEXT NOT NULL, p4port TEXT, client TEXT, p4user TEXT NOT NULL, root TEXT NOT NULL UNIQUE,
  compile_commands TEXT NOT NULL, build_root TEXT, swarm_url TEXT, settings TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL, created_by TEXT, created_at TEXT, updated_at TEXT);
```

After `ANCHOR_KINDS = …` add:

```python
# a workspace's own columns (spec 2026-10-31 §5): compile_commands is JSON ("auto", a path or a list), settings YAML
WORKSPACE_FIELDS = ("name", "vcs", "p4port", "client", "p4user", "root", "compile_commands", "build_root", "swarm_url",
                    "settings")
```

In `Store.__init__`, after the `llm_calls` migration:

```python
            reviews = {r[1] for r in self._db.execute("PRAGMA table_info(reviews)")}
            if "workspace_id" not in reviews:        # databases made before workspaces (spec 2026-10-31 §12)
                self._db.execute("ALTER TABLE reviews ADD COLUMN workspace_id INTEGER")
```

Replace `create_review`, and add the workspace methods after `get_review`:

```python
    def create_review(self, title: str, created_by: str, cls: list[int], workspace_id: int | None = None) -> int:
        cur = self._exec("INSERT INTO reviews(title, created_by, created_at, status, risk, workspace_id) "
                         "VALUES(?,?,?,?,?,?)", (title, created_by, _now(), "queued", None, workspace_id))
        rid = int(cur.lastrowid)
        for cl in sorted(set(cls)):
            self._exec("INSERT INTO review_cls(review_id, cl, status) VALUES(?,?,?)", (rid, cl, "unknown"))
        return rid
```

```python
    def adopt_reviews(self, wid: int) -> int:
        """Reviews made before workspaces belong to the seed (spec 2026-10-31 §12); how many there were."""
        return self._exec("UPDATE reviews SET workspace_id=? WHERE workspace_id IS NULL", (wid,)).rowcount

    def review_count(self, wid: int) -> int:
        return self._all("SELECT COUNT(*) AS n FROM reviews WHERE workspace_id=?", (wid,))[0]["n"]

    # ---- workspaces (spec 2026-10-31 §5) -----------------------------------------
    def add_workspace(self, fields: dict, source: str, created_by: str) -> int:
        """A new workspace (`source` "config" for the seed, "ui" for one added on the Workspaces page); a name or root
        another has raises sqlite3.IntegrityError."""
        now = _now()
        cols = WORKSPACE_FIELDS + ("source", "created_by", "created_at", "updated_at")
        cur = self._exec(f"INSERT INTO workspaces({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
                         tuple(fields.get(k) for k in WORKSPACE_FIELDS) + (source, created_by, now, now))
        return int(cur.lastrowid)

    def update_workspace(self, wid: int, fields: dict) -> None:
        sets = ", ".join(f"{k}=?" for k in WORKSPACE_FIELDS)
        self._exec(f"UPDATE workspaces SET {sets}, updated_at=? WHERE id=?",
                   tuple(fields.get(k) for k in WORKSPACE_FIELDS) + (_now(), wid))

    def delete_workspace(self, wid: int) -> None:
        self._exec("DELETE FROM workspaces WHERE id=?", (wid,))

    def get_workspace(self, wid: int) -> dict | None:
        rows = self._all("SELECT * FROM workspaces WHERE id=?", (wid,))
        return rows[0] if rows else None

    def list_workspaces(self) -> list[dict]:
        return self._all("SELECT * FROM workspaces ORDER BY name")

    def seed_workspace(self) -> dict | None:
        """The workspace registered from tortoise.yaml."""
        rows = self._all("SELECT * FROM workspaces WHERE source='config' ORDER BY id")
        return rows[0] if rows else None
```

After `kv_put` add:

```python
    def kv_delete_scope(self, scope: str) -> None:
        """Every entry kept for one workspace: its keys hold `:<scope>` as a whole segment (spec 2026-10-31 §5)."""
        self._exec("DELETE FROM kv WHERE key LIKE ? OR key LIKE ?", (f"%:{scope}", f"%:{scope}:%"))
```

- [ ] **Step 4: Run the store tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_store.py -q`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd backend
git add codetortoise/store.py tests/test_store.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(store): workspaces, the workspace a review belongs to, and a workspace's store entries

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: Bundle plumbing — shared parts, a folder and a key scope per workspace

**Files:**
- Modify: `backend/codetortoise/services.py`
- Modify: `backend/codetortoise/toolchain/toolchain.py:17,79-97`
- Modify: `backend/codetortoise/toolchain/libclang.py`
- Modify: `backend/codetortoise/vcs/p4runner.py:32-48`
- Modify: `backend/codetortoise/sinks.py:12,48-58`
- Modify: `backend/codetortoise/pipeline.py:278,614-686`
- Create: `backend/tests/test_bundle.py`
- Modify: `backend/tests/test_p4source.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces:
  - `services.strip_flags_key(root: Path | str, scope: str = "") -> str` — `"strip_flags:<scope>"`, or `"strip_flags:<root>"` without a scope.
  - `build_services(cfg, llm=None, source=None, strong=None, *, store: Store | None = None, ledger: Ledger | None = None, home: Path | None = None, scope: str = "") -> Services` — with no keyword arguments it behaves exactly as today.
  - `Services.scope: str = ""` (the last field).
  - `LayersProvider(cfg, index, store, llm, ledger=None, scope="")`.
  - `Toolchain(cfg, cdb, work_dir, root=None, data_dir=None)`.
  - `libclang.library_info(path: str | None) -> LibclangInfo`.
  - `P4Runner(p4port, client, p4_bin="p4", timeout=120, cwd=None, user=None)`; `.user`.
  - `sinks.marks_key(scope: str = "") -> str`; `sinks.marks(store, scope="")`; `sinks.set_mark(store, label, on, scope="")`.
  - `pipeline.AiPool(workers: int)` with `.executor`, `.jobs: dict[int, list[dict]]`, `.ids: dict[int, int]`, `.lock`.
  - `JobRunner(svc, pool: AiPool | None = None)`; `.pool`; `.ai_jobs` (the pool's `jobs`); `.busy() -> str | None`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_bundle.py`:

```python
"""A workspace's bundle on a server of many (spec 2026-10-31 §6): shared store, ledger and AI pool; its own folder and
store-entry keys; its own libclang even when the process loaded another."""
import threading

from helpers import make_config, make_services

from codetortoise.config import ToolchainConfig
from codetortoise.llm.ledger import Ledger
from codetortoise.pipeline import AiPool, JobRunner
from codetortoise.services import build_services
from codetortoise.sinks import marks, set_mark
from codetortoise.store import Store
from codetortoise.toolchain import libclang as lc
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain


def test_bundles_share_the_store_and_ledger_and_keep_their_index_toolchain_and_entries_apart(fx, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    cfg = make_config(fx, data)
    store = Store(data / "tortoise.db")
    ledger = Ledger(store, cfg.llm.budget)
    a = build_services(cfg, store=store, ledger=ledger, home=data / "workspaces" / "1", scope="ws1")
    b = build_services(cfg, store=store, ledger=ledger, home=data / "workspaces" / "2", scope="ws2")
    assert a.store is b.store is store and a.ledger is b.ledger is ledger
    assert a.index.db_path == data / "workspaces" / "1" / "symbols.db"
    assert a.toolchain.work_dir == data / "workspaces" / "1" / "toolchain"
    assert a.toolchain.data_dir == data                     # where fetch-libclang puts libraries
    a.remember_stripped(["-mfoo"])
    assert store.kv_get("strip_flags:ws1") == ["-mfoo"] and store.kv_get("strip_flags:ws2") is None
    assert build_services(cfg, store=store, ledger=ledger, home=data / "workspaces" / "1",
                          scope="ws1").toolchain.strip >= {"-mfoo"}
    a.build_index()
    a.layers.get()
    keys = [r["key"] for r in store._all("SELECT key FROM kv WHERE key LIKE 'layers:%'")]
    assert keys and all(":ws1:" in k for k in keys)


def test_a_bundle_built_on_its_own_keeps_the_single_workspace_folders_and_keys(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    assert svc.index.db_path == tmp_path / "symbols.db" and svc.toolchain.data_dir == tmp_path
    svc.remember_stripped(["-mbar"])
    assert svc.store.kv_get(f"strip_flags:{fx.root}") == ["-mbar"]


def test_shared_sink_marks_are_kept_per_workspace(tmp_path):
    store = Store(tmp_path / "t.db")
    set_mark(store, "Uart::errors", True, "ws1")
    assert marks(store, "ws1") == ["Uart::errors"] and marks(store, "ws2") == [] and marks(store) == []
    assert store.kv_get("sink_marks:ws1") == ["Uart::errors"]
    set_mark(store, "log_t::buf", True)
    assert store.kv_get("sink_marks") == ["log_t::buf"]                 # a bundle on its own: the one entry, as before


def test_the_library_this_process_has_is_described_in_place(monkeypatch):
    bundled = lc.LibclangInfo(path="/b/libclang.so", version="clang version 1", vendor=False)
    monkeypatch.setattr(lc, "_loaded", bundled)
    assert lc.library_info(None) is bundled
    vendor = lc.LibclangInfo(path="/v/libclang.so.19", version="clang version 19", vendor=True)
    monkeypatch.setattr(lc, "_loaded", vendor)
    assert lc.library_info("/v/libclang.so.19") is vendor


def test_a_toolchain_that_picks_another_library_than_the_process_has_still_prepares(monkeypatch, tmp_path):
    vendor = lc.LibclangInfo(path="/v/libclang.so.19", version="clang version 19", vendor=True)
    monkeypatch.setattr(lc, "_loaded", vendor)        # another workspace's toolchain loaded its own library here
    tc = Toolchain(ToolchainConfig(), CompileDb([]), tmp_path / "tc", data_dir=tmp_path)
    tc.prepare()                                      # chooses the bundled library: described from a worker process
    assert tc.choice.kind == "bundled" and tc.libclang.vendor is False
    assert tc.libclang.path != vendor.path and tc.libclang.version.startswith("clang version")
    assert lc._loaded is vendor                       # this process keeps the library it has


def test_queues_share_one_ai_pool_and_its_jobs(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    pool = AiPool(2)
    a, b = JobRunner(svc, pool), JobRunner(svc, pool)
    done = threading.Event()
    job = a.submit_ai(7, "amy", "flow", "FL1", done.set)
    assert done.wait(10) and b.ai_jobs[7] == [job] and job["id"] == 1
    assert b.submit_ai(7, "bob", "flow", "FL2", lambda: None)["id"] == 2     # ids count per review, across queues


def test_a_queue_is_busy_while_a_review_or_an_index_build_waits_or_runs(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    reviews = JobRunner(svc)                            # not started: what is submitted waits
    assert reviews.busy() is None
    reviews.submit_review(svc.store.create_review("t", "owner", [101]))
    assert reviews.busy() == "a review is running in this workspace; try again when it finishes"
    index = JobRunner(svc)
    index.submit_index()
    assert index.busy() == "the symbol index is being built in this workspace; try again when it finishes"
    index.start()
    index.stop()
    index._thread.join(60)
    assert index.busy() is None
```

Append to `backend/tests/test_p4source.py`:

```python
def test_reads_run_as_the_workspaces_user_and_a_sign_in_as_whoever_signs_in(monkeypatch):
    import subprocess
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: seen.append(cmd) or Completed(b""))
    r = P4Runner("p4:1666", "ws", user="amy")
    r.run("info")
    r.print_text("//depot/a.c#1")
    r.login_check("bob", "pw")
    assert seen[0][:7] == seen[1][:7] == ["p4", "-p", "p4:1666", "-c", "ws", "-u", "amy"]
    assert seen[2][:7] == ["p4", "-p", "p4:1666", "-c", "ws", "-u", "bob"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bundle.py tests/test_p4source.py -q`
Expected: collection error `ImportError: cannot import name 'AiPool' from 'codetortoise.pipeline'` for test_bundle; `TypeError: P4Runner.__init__() got an unexpected keyword argument 'user'` for the new P4 test.

- [ ] **Step 3: Implement**

`backend/codetortoise/vcs/p4runner.py` — the constructor and `_base`:

```python
class P4Runner:
    def __init__(self, p4port: str, client: str | None, p4_bin: str = "p4", timeout: float = 120,
                 cwd: str | Path | None = None, user: str | None = None):
        self.p4port = p4port
        self.client = client
        self.p4_bin = p4_bin
        self.timeout = timeout
        # p4 runs from the workspace, so it also reads the P4CONFIG file there (P4CHARSET, P4TICKETS, P4TRUST, ...)
        self.cwd = str(cwd) if cwd else None
        # the user reads run as, passed explicitly so workspaces of different users don't share P4USER (spec
        # 2026-10-31 §6); a sign-in passes its own
        self.user = user

    def _base(self, user: str | None = None) -> list[str]:
        cmd = [self.p4_bin, "-p", self.p4port]
        if self.client:
            cmd += ["-c", self.client]
        if user or self.user:
            cmd += ["-u", user or self.user]
        return cmd
```

`backend/codetortoise/toolchain/libclang.py` — add `import multiprocessing as mp` and `import threading` to the imports and `from concurrent.futures import ProcessPoolExecutor`; after `_loaded: LibclangInfo | None = None` add `_lock = threading.Lock()`; after `load_libclang` add:

```python
def library_info(path: str | None) -> LibclangInfo:
    """The library a workspace parses with, described: loaded here when this process has none yet (or has this one);
    else described from a worker process, since a process loads one libclang and workspaces may each choose another
    (spec 2026-10-31 §6). Every parse already runs in worker processes that load the request's library."""
    with _lock:
        if _loaded is None:
            return load_libclang(path)
        same = _loaded.path == path if path else not _loaded.vendor
    if same:
        return _loaded
    method = "forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn"
    with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context(method)) as pool:
        return pool.submit(load_libclang, path).result(timeout=120)
```

`backend/codetortoise/toolchain/toolchain.py` — line 17 imports `library_info` instead of `load_libclang`:

```python
from codetortoise.toolchain.libclang import LibclangChoice, LibclangInfo, find_libclang, library_info
```

and the constructor and `prepare` become:

```python
    def __init__(self, cfg: ToolchainConfig, cdb: CompileDb, work_dir: Path, root: Path | None = None,
                 data_dir: Path | None = None):
        self.cfg = cfg
        self.cdb = cdb
        self.work_dir = Path(work_dir)
        self.root = canon(str(root)) if root else None
        self.strip: set[str] = set(cfg.strip_flags)
        self.libclang: LibclangInfo | None = None
        self._groups: dict[tuple, Group] = {}
        self._machines: dict[str, str | None] = {}
        # where fetch-libclang puts libraries: the server's data folder (a workspace's own folder sits below it)
        self.data_dir = Path(data_dir) if data_dir is not None else self.work_dir.parent
        self.choice: LibclangChoice | None = None    # the library this workspace parses with by default
        self.samples: dict[tuple, str] = {}          # Health's sample parse per group, once per process

    def prepare(self) -> None:
        """Idempotent: chooses and describes this workspace's default library (loading it here when the process has no
        other). Every parse runs in worker processes that load the request's library; compilers are queried lazily,
        per group."""
        if self.libclang is None:
            self.choice = find_libclang(self.cfg, data_dir=self.data_dir)
            self.libclang = library_info(self.choice.path)
```

`backend/codetortoise/sinks.py` — replace `MARKS_KEY`'s comment and `marks`/`set_mark`:

```python
MARKS_KEY = "sink_marks"          # the store's kv row: the owner's marked labels, for every review of the workspace


def marks_key(scope: str = "") -> str:
    """The marks' kv row: one per workspace on a server of many (spec 2026-10-31 §5); a bundle on its own keeps the
    single row it had."""
    return f"{MARKS_KEY}:{scope}" if scope else MARKS_KEY
```

```python
def marks(store: Any, scope: str = "") -> list[str]:
    got = store.kv_get(marks_key(scope))
    return sorted(x for x in got if isinstance(x, str)) if isinstance(got, list) else []


def set_mark(store: Any, label: str, on: bool, scope: str = "") -> list[str]:
    """Mark or unmark `label` for every review of the workspace from the next run; the marks after."""
    cur = set(marks(store, scope))
    cur = cur | {label} if on else cur - {label}
    store.kv_put(marks_key(scope), sorted(cur))
    return sorted(cur)
```

`backend/codetortoise/services.py`:
- add `from pathlib import Path` to the imports;
- `LayersProvider` takes and keys by the scope:

```python
    def __init__(self, cfg: Config, index: SymbolIndex, store: Store, llm: LlmClient | None,
                 ledger: Ledger | None = None, scope: str = ""):
        self.cfg, self.index, self.store, self.llm, self.ledger, self.scope = cfg, index, store, llm, ledger, scope
        self._lock = threading.Lock()
        self._model: LayerModel | None = None

    def _key(self) -> str:
        where = self.scope or self.cfg.workspace.root
        return f"layers:v{layers_mod.ALGORITHM_VERSION}:{where}:{self.index.generation()}"
```

- `Services` gains a last field `scope: str = ""                              # keys its store entries on a server of many (spec 2026-10-31 §5)` (after `swarm_override`), and `remember_stripped` writes `self.store.kv_put(strip_flags_key(self.cfg.workspace.root, self.scope), sorted(self.toolchain.strip))`;
- before `make_llm` add:

```python
def strip_flags_key(root: Path | str, scope: str = "") -> str:
    """The kv row of the flags libclang rejected in a workspace: by its scope on a server of many (spec 2026-10-31 §5),
    by its root for a bundle on its own."""
    return f"strip_flags:{scope or root}"
```

- `build_services` becomes:

```python
def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | None = None,
                   strong: LlmClient | None = None, *, store: Store | None = None, ledger: Ledger | None = None,
                   home: Path | None = None, scope: str = "") -> Services:
    """A workspace's bundle (spec 2026-10-31 §6). A server of many passes what its workspaces share (`store`,
    `ledger`), the workspace's own folder (`home`: its symbol index and toolchain files) and the scope keying its store
    entries; without them the bundle stands alone, as a single-workspace server's did."""
    data = cfg.server.data_dir
    data.mkdir(parents=True, exist_ok=True)
    home = home if home is not None else data
    store = store if store is not None else Store(data / "tortoise.db")
    index = SymbolIndex(home / "symbols.db")
    cdb = load_databases(cfg.workspace.compile_commands, cfg.workspace.root, cfg.workspace.build_root)
    tc = Toolchain(cfg.toolchain, cdb, home / "toolchain", root=cfg.workspace.root, data_dir=data)
    tc.strip.update(store.kv_get(strip_flags_key(cfg.workspace.root, scope)) or [])
    llm = llm if llm is not None else make_llm(cfg)
    p4 = None
    if source is None:
        if cfg.workspace.vcs == "git":
            source = GitFixtureSource(cfg.workspace.root)
        else:
            p4 = P4Runner(cfg.workspace.p4port or "", cfg.workspace.client, cfg.workspace.p4_bin,
                          cwd=cfg.workspace.root, user=cfg.owner or None)
            source = P4Source(p4)
    ledger = ledger if ledger is not None else Ledger(store, cfg.llm.budget, cfg.llm.request_log,
                                                      cfg.llm.request_log_days)
    return Services(cfg=cfg, store=store, source=source, index=index, cdb=cdb, toolchain=tc, llm=llm,
                    layers=LayersProvider(cfg, index, store, llm, ledger, scope), p4=p4, ledger=ledger,
                    strong=strong if strong is not None else make_strong(cfg), scope=scope)
```

`backend/codetortoise/pipeline.py`:
- add `from collections import Counter` to the imports;
- line 278: `marked=sink_marks(store, svc.scope))`;
- replace `class JobRunner` (through `_loop`) with:

```python
class AiPool:
    """The AI worker pool and its job registry, shared by every workspace's queue so `llm.concurrency` stays a
    server-wide limit (spec 2026-10-31 §6). Review ids are global, so jobs are kept by review."""

    def __init__(self, workers: int):
        self.executor = ThreadPoolExecutor(max(1, workers), thread_name_prefix="tortoise-ai")
        self.jobs: dict[int, list[dict]] = {}
        self.ids: dict[int, int] = {}
        self.lock = threading.Lock()


class JobRunner:
    """A workspace's background worker: its reviews and index rebuilds run one at a time."""

    def __init__(self, svc: Services, pool: AiPool | None = None):
        self.svc = svc
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tortoise-jobs")
        self.index_building = False
        # AI jobs (explanations, @tortoise) run beside reviews, not behind them, in the pool every workspace shares
        self.pool = pool if pool is not None else AiPool(svc.cfg.llm.concurrency)
        self.ai_jobs = self.pool.jobs
        self._pending: Counter[str] = Counter()          # jobs queued or running, by kind
        self._pending_lock = threading.Lock()

    def submit_ai(self, rid: int, user: str, kind: str, target: str, fn: Callable[[], None]) -> dict:
        """Queue one AI job for review `rid`; its status ("running", "done", "failed", "refused") is kept in
        `ai_jobs` for the review's AI view."""
        with self.pool.lock:
            jobs = self.ai_jobs.setdefault(rid, [])
            self.pool.ids[rid] = self.pool.ids.get(rid, 0) + 1    # never reused, though only the last 50 are kept
            job = {"id": self.pool.ids[rid], "user": user, "kind": kind, "target": target, "status": "running",
                   "error": None}
            jobs.append(job)
            del jobs[:-50]
        self._dispatch_ai(job, fn)
        return job

    def _dispatch_ai(self, job: dict, fn: Callable[[], None]) -> None:
        self.pool.executor.submit(self._run_ai, job, fn)
```

keep `_run_ai` and `start` as they are, then:

```python
    def _count(self, kind: str, n: int) -> None:
        with self._pending_lock:
            self._pending[kind] += n

    def busy(self) -> str | None:
        """Why this workspace's bundle can't be replaced now (an edit swaps it, spec 2026-10-31 §6), or None."""
        with self._pending_lock:
            if self._pending["review"]:
                return "a review is running in this workspace; try again when it finishes"
            if self._pending["index"]:
                return "the symbol index is being built in this workspace; try again when it finishes"
        return None

    def submit_review(self, rid: int, fresh: bool = False) -> None:
        self.svc.store.set_review_status(rid, "queued")
        self._count("review", 1)
        self._q.put(("review", (rid, fresh)))

    def submit_index(self) -> None:
        self._count("index", 1)
        self._q.put(("index", None))

    def stop(self) -> None:
        self._q.put(None)

    def _loop(self) -> None:
        while True:
            job = self._q.get()
            if job is None:
                return
            kind, arg = job
            try:
                if kind == "review":
                    run_review(arg[0], self.svc, fresh=arg[1])
                elif kind == "index":
                    self.index_building = True
                    self.svc.build_index()
            except Exception:
                log.error("job %s failed: %s", job, traceback.format_exc())
            finally:
                self.index_building = False
                self._count(kind, -1)
```

- [ ] **Step 4: Run the new tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bundle.py tests/test_p4source.py -q`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff clean. (`InlineRunner` in `tests/test_web.py` overrides `submit_review`, `submit_index` and `_dispatch_ai`, so it never counts jobs; nothing else changes for it.)

- [ ] **Step 5: Commit**

```bash
cd backend
git add codetortoise/services.py codetortoise/toolchain/toolchain.py codetortoise/toolchain/libclang.py \
  codetortoise/vcs/p4runner.py codetortoise/sinks.py codetortoise/pipeline.py tests/test_bundle.py tests/test_p4source.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(services): a bundle per workspace — shared store, ledger and AI pool; its own folder, keys, user and libclang

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: The registry — every workspace, its bundle and its queue

**Files:**
- Create: `backend/codetortoise/workspaces.py`
- Create: `backend/tests/test_workspaces.py`
- Modify: `backend/tests/conftest.py` (a second fixture workspace)

**Interfaces:**
- Consumes: Task 1 (`effective_config`, `seed_name`, `valid_name`, `ConfigError`), Task 2 (the `Store` workspace methods, `adopt_reviews`, `review_count`, `kv_delete_scope`, `create_review(..., workspace_id=)`), Task 3 (`build_services(..., store=, ledger=, home=, scope=)`, `strip_flags_key`, `marks_key`, `MARKS_KEY`, `AiPool`, `JobRunner(svc, pool)`, `JobRunner.busy()`, `P4Runner(..., user=)`).
- Produces (module `codetortoise.workspaces`):
  - `LOCAL = "local"`, `LOADING = "loading"`, `NO_WORKSPACE` (the message naming both ways in)
  - `class Conflict(Exception)` (HTTP 409), `class Invalid(Exception)` (HTTP 422)
  - `server_of(p4port: str | None) -> str`; `scope_of(wid: int) -> str` (`"ws<id>"`)
  - `@dataclass Workspace(id, name, server, owner, seed, cfg, svc=None, runner=None, reason=LOADING, checks=[], loaded=Event())` with property `ready`; `loaded` is set once its bundle has been built (or has failed to)
  - `class Registry` with:
    - `Registry.open(base: Config, spawn=None, runner_class=JobRunner) -> Registry` (classmethod: store, ledger, AI pool, LLM clients)
    - `Registry.single(svc: Services, runner: JobRunner) -> Registry` (classmethod: one bundle built on its own, as the seed)
    - attributes `base`, `store`, `ledger`, `pool`
    - `load() -> None`; `all() -> list[Workspace]` (by name); `get(wid) -> Workspace | None`; `seed() -> Workspace | None`; `for_review(review: dict) -> Workspace | None`; `servers() -> list[str]`; `owners(server) -> set[str]`; `home(wid) -> Path`
    - `settle(ws, timeout=120.0) -> None` (waits while its bundle is still being built); `recheck(ws, deep=False) -> HealthReport | None`
    - `keep_ticket(server, user, ticket) -> None`; `login_runner(server) -> P4Runner | None`
    - `add(fields: dict, by: str) -> Workspace`; `edit(wid, fields) -> Workspace`; `remove(wid) -> None` (raise `Invalid`, `Conflict`, or `KeyError` for an unknown id)
    - `tool_workspace(name: str | None) -> Workspace` (raises `ConfigError`)
  - `fields` dicts have the keys of `store.WORKSPACE_FIELDS`, with `compile_commands` as JSON text.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/conftest.py`, after the `fx` fixture:

```python
@pytest.fixture(scope="session")
def fx_b(tmp_path_factory):
    """A second fixture workspace, for a server hosting two."""
    return build_fixture(tmp_path_factory.mktemp("fixture_b"))
```

Create `backend/tests/test_workspaces.py`:

```python
"""The workspaces one server hosts (spec 2026-10-31 §4–§6, §11, §12)."""
import json
import threading

import pytest
from helpers import make_config, make_services
from test_web import InlineRunner

from codetortoise import workspaces
from codetortoise.config import ConfigError
from codetortoise.sinks import marks, set_mark
from codetortoise.toolchain.libclang import find_libclang
from codetortoise.workspaces import LOCAL, Conflict, Invalid, Registry


def server(fx, tmp_path, **overrides):
    """A registry as `serve` opens it, building bundles inline."""
    return Registry.open(make_config(fx, tmp_path / "data", **overrides), spawn=lambda fn: fn(),
                         runner_class=InlineRunner)


def fields(root, name="b", **kw):
    return {"name": name, "vcs": "git", "p4port": None, "client": None, "p4user": "owner", "root": str(root),
            "compile_commands": json.dumps("auto"), "build_root": None, "swarm_url": None, "settings": "", **kw}


def test_the_seed_is_registered_from_the_file_and_refreshed_at_each_start(fx, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    [ws] = reg.all()
    assert (ws.id, ws.name, ws.server, ws.owner, ws.seed) == (1, fx.root.name, LOCAL, "owner", True)
    assert ws.ready and ws.svc.index.db_path == tmp_path / "data" / "workspaces" / "1" / "symbols.db"
    assert ws.svc.index.generation() > 0                        # an empty index is built when the bundle loads
    again = server(fx, tmp_path, owner="amy")
    again.load()
    [ws2] = again.all()
    assert (ws2.id, ws2.owner) == (1, "amy") and again.store.get_workspace(1)["p4user"] == "amy"


def test_a_request_right_after_startup_waits_for_its_workspace_to_load(fx, tmp_path):
    reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=lambda fn: threading.Timer(0.3, fn).start(),
                        runner_class=InlineRunner)
    reg.load()
    ws = reg.seed()
    assert ws.reason == workspaces.LOADING and not ws.loaded.is_set()
    reg.settle(ws)
    assert ws.ready and ws.loaded.is_set()


def test_with_no_workspace_the_server_names_both_ways_in(fx, tmp_path):
    with pytest.raises(ConfigError, match="`workspace:` section.*data folder"):
        server(fx, tmp_path, workspace=None).load()
    server(fx, tmp_path).load()                                 # an earlier run stored the seed
    later = server(fx, tmp_path, workspace=None)
    later.load()
    [ws] = later.all()
    assert ws.name == fx.root.name and not ws.seed and ws.ready  # served from its row, editable now


def test_a_workspace_whose_bundle_fails_to_build_is_kept_not_ready_with_the_reason(fx, fx_b, tmp_path, monkeypatch):
    reg = server(fx, tmp_path)
    reg.load()

    def broken(*a, **k):
        raise OSError("compile database unreadable")
    monkeypatch.setattr(workspaces, "build_services", broken)
    ws = reg.add(fields(fx_b.root), "owner")
    assert ws.svc is None and not ws.ready
    assert ws.reason == "could not load: OSError: compile database unreadable"
    assert reg.get(ws.id) is ws and reg.get(1).ready             # the others are untouched


def test_a_failing_hard_check_keeps_a_workspace_not_ready_with_its_reason(fx, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    empty = tmp_path / "empty"
    empty.mkdir()
    ws = reg.add(fields(empty, name="empty"), "owner")
    assert ws.svc is not None and not ws.ready
    assert ws.reason == "compile_commands: no compile database found (auto)"
    assert any(c.name == "compile_commands" and not c.ok for c in ws.checks)


def test_adding_and_editing_check_the_name_root_and_perforce_fields(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    for bad, match in ((fields(fx_b.root, name="a/b"), "name"), (fields(fx_b.root, name="x" * 41), "name"),
                       (fields("relative/b"), "full path"), (fields(fx_b.root, vcs="p4", client="amy-b"), "P4PORT"),
                       (fields(fx_b.root, settings="server: {port: 1}"), "settings")):
        with pytest.raises(Invalid, match=match):
            reg.add(bad, "owner")
    with pytest.raises(Conflict, match=f"a workspace named {fx.root.name} already exists"):
        reg.add(fields(fx_b.root, name=fx.root.name), "owner")
    ws = reg.add(fields(fx_b.root, p4port="second:1666"), "owner")
    assert (ws.id, ws.server, ws.seed, ws.ready) == (2, "second:1666", False, True)
    assert reg.store.get_workspace(2)["created_by"] == "owner" and reg.store.get_workspace(2)["source"] == "ui"
    assert reg.servers() == [LOCAL, "second:1666"] and reg.owners("second:1666") == {"owner"}
    edited = reg.edit(2, fields(fx_b.root, name="b2", p4port="second:1666", p4user="amy"))
    assert reg.get(2) is edited and (edited.name, edited.owner, edited.ready) == ("b2", "amy", True)
    ws.runner._thread.join(10)
    assert not ws.runner._thread.is_alive()                     # the old bundle's queue stopped
    with pytest.raises(Conflict, match="set in tortoise.yaml"):
        reg.edit(1, fields(fx.root, name=fx.root.name))
    with pytest.raises(Conflict, match="set in tortoise.yaml"):
        reg.remove(1)
    with pytest.raises(KeyError):
        reg.edit(99, fields(fx_b.root))


def test_an_edit_waits_for_the_workspaces_queue(fx, fx_b, tmp_path, monkeypatch):
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.add(fields(fx_b.root), "owner")
    monkeypatch.setattr(ws.runner, "busy", lambda: "a review is running in this workspace; try again when it finishes")
    with pytest.raises(Conflict, match="a review is running in this workspace; try again when it finishes"):
        reg.edit(ws.id, fields(fx_b.root, name="b2"))
    with pytest.raises(Conflict, match="a review is running in this workspace"):
        reg.remove(ws.id)
    assert reg.get(ws.id) is ws and reg.store.get_workspace(ws.id)["name"] == "b"


def test_a_workspace_with_reviews_is_kept(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.add(fields(fx_b.root), "owner")
    reg.store.create_review("t", "owner", [101], workspace_id=ws.id)
    with pytest.raises(Conflict, match="has 1 review"):
        reg.remove(ws.id)


def test_a_root_in_another_spelling_is_the_same_root_and_a_removed_workspace_leaves_nothing_behind(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    link = tmp_path / "link"
    link.symlink_to(fx_b.root)
    ws = reg.add(fields(fx_b.root), "owner")
    for spelling in (f"{fx_b.root}/", str(fx_b.root.parent / "x" / ".." / fx_b.root.name), str(link)):
        with pytest.raises(Conflict, match="the workspace b already has the root"):
            reg.add(fields(spelling, name="again"), "owner")
    ws.svc.remember_stripped(["-mfoo"])
    set_mark(reg.store, "Uart::errors", True, ws.svc.scope)
    home = tmp_path / "data" / "workspaces" / str(ws.id)
    assert (home / "symbols.db").exists()
    reg.remove(ws.id)
    assert reg.get(ws.id) is None and reg.store.get_workspace(ws.id) is None and not home.exists()
    again = reg.add(fields(fx_b.root), "owner")
    assert again.id == ws.id + 1                                 # ids never repeat
    assert again.svc.toolchain.strip == set() and marks(reg.store, again.svc.scope) == []
    assert reg.store.kv_get(f"strip_flags:ws{ws.id}") is None and reg.store.kv_get(f"sink_marks:ws{ws.id}") is None


def test_the_first_start_after_the_upgrade_keeps_what_the_single_workspace_server_had(fx, tmp_path):
    data = tmp_path / "data"
    old = make_services(fx, data)                                # today's single-workspace server, same data folder
    rid = old.store.create_review("t", "owner", [101])
    set_mark(old.store, "Uart::errors", True)
    old.remember_stripped(["-mfoo"])
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.seed()
    review = reg.store.get_review(rid)
    assert review["workspace_id"] == ws.id and reg.for_review(review) is ws
    assert marks(reg.store, ws.svc.scope) == ["Uart::errors"] and "-mfoo" in ws.svc.toolchain.strip
    fetched = data / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2"    # what fetch-libclang leaves
    fetched.parent.mkdir(parents=True)
    fetched.write_bytes(b"")
    (fetched.parent / "clang" / "23" / "include").mkdir(parents=True)
    got = find_libclang(ws.svc.toolchain.cfg, data_dir=ws.svc.toolchain.data_dir)
    assert (got.kind, got.path) == ("fetched", str(fetched))     # still found from the seed's own toolchain folder


def test_the_owners_swarm_ticket_reaches_every_workspace_they_own_on_that_server(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root, p4port="second:1666"), "owner")
    reg.keep_ticket("second:1666", "owner", "T2")
    assert b.svc.owner_ticket == "T2" and reg.seed().svc.owner_ticket is None
    edited = reg.edit(b.id, fields(fx_b.root, name="b2", p4port="second:1666"))
    assert edited.svc.owner_ticket == "T2"                       # a bundle built later gets it too


def test_sign_in_runs_p4_from_a_perforce_workspace_on_that_server(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    assert reg.login_runner(LOCAL) is None                       # git only: nothing checks a password there
    ws = reg.add(fields(fx_b.root, vcs="p4", p4port="ssl:p4b:1666", client="amy-b", p4user="amy"), "owner")
    assert not ws.ready and ws.reason.startswith("p4 client")    # no Perforce here: the client check fails
    r = reg.login_runner("ssl:p4b:1666")
    assert (r.p4port, r.client, r.cwd, r.user) == ("ssl:p4b:1666", None, str(fx_b.root), None)
    assert ws.svc.p4.user == "amy"                               # its reads run as its owner


def test_a_tool_works_on_the_named_workspace_else_the_seed_else_the_only_one(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    reg.add(fields(fx_b.root), "owner")
    data = tmp_path / "data"
    assert Registry.open(make_config(fx, data)).tool_workspace("b").name == "b"
    assert Registry.open(make_config(fx, data)).tool_workspace(None).seed
    bare = make_config(fx, data, workspace=None)
    with pytest.raises(ConfigError, match=rf"several workspaces: name one with --workspace \(b, {fx.root.name}\)"):
        Registry.open(bare).tool_workspace(None)
    with pytest.raises(ConfigError, match=rf"no workspace named nope \(there are: b, {fx.root.name}\)"):
        Registry.open(bare).tool_workspace("nope")
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_workspaces.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'codetortoise.workspaces'`.

- [ ] **Step 3: Implement**

Create `backend/codetortoise/workspaces.py`:

```python
"""The workspaces one server hosts (spec 2026-10-31-multi-workspace-server): each with its effective configuration, its
bundle of services and its job queue, from the `workspaces` table and the seed tortoise.yaml describes."""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from codetortoise.config import Config, ConfigError, effective_config, seed_name, valid_name
from codetortoise.health import Check, HealthReport, run_health
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger
from codetortoise.paths import canon
from codetortoise.pipeline import AiPool, JobRunner
from codetortoise.services import Services, build_services, make_llm, make_strong, strip_flags_key
from codetortoise.sinks import MARKS_KEY, marks_key
from codetortoise.store import Store
from codetortoise.vcs.p4runner import P4Runner

LOCAL = "local"            # the Perforce server of a workspace with no p4port (§5)
LOADING = "loading"        # a workspace's reason while its bundle builds
NO_WORKSPACE = ("no workspace to serve: add a `workspace:` section to tortoise.yaml, or set server.data_dir to a data "
                "folder that already holds one")
log = logging.getLogger(__name__)


class Conflict(Exception):
    """Refused because of another workspace, a review or a running job (HTTP 409)."""


class Invalid(Exception):
    """A value a workspace can't take (HTTP 422)."""


def server_of(p4port: str | None) -> str:
    """A workspace's Perforce server: its p4port as written, or `local` (§5)."""
    return p4port or LOCAL


def scope_of(wid: int) -> str:
    """The scope keying a workspace's store entries (§5)."""
    return f"ws{wid}"


def _stored(cc) -> str:
    """`workspace.compile_commands` as the workspaces table holds it: JSON text."""
    if isinstance(cc, list):
        return json.dumps([str(p) for p in cc])
    return json.dumps(cc if cc == "auto" else str(cc))


@dataclass
class Workspace:
    id: int
    name: str
    server: str
    owner: str                        # its p4user: owner rights go to whoever is signed in to its server as them (§7)
    seed: bool                        # described by tortoise.yaml: read-only in the UI (§4)
    cfg: Config                       # its effective configuration (§4)
    svc: Services | None = None       # its bundle, once built
    runner: JobRunner | None = None   # its job queue
    reason: str | None = LOADING      # why it isn't ready; None when it is
    checks: list[Check] = field(default_factory=list)
    loaded: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)   # set once it built

    @property
    def ready(self) -> bool:
        return self.svc is not None and self.reason is None


class Registry:
    """Every workspace the server hosts, each with its bundle and job queue (§6). The database, the LLM clients, the
    ledger and the AI pool are shared."""

    def __init__(self, base: Config, store: Store, ledger: Ledger, pool: AiPool, llm: LlmClient | None = None,
                 strong: LlmClient | None = None, spawn: Callable[[Callable[[], None]], None] | None = None,
                 runner_class: type[JobRunner] = JobRunner):
        self.base, self.store, self.ledger, self.pool = base, store, ledger, pool
        self.llm, self.strong = llm, strong
        self.spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=True, name="tortoise-load").start())
        self.runner_class = runner_class
        self._lock = threading.Lock()
        self._ws: dict[int, Workspace] = {}
        self._tickets: dict[tuple[str, str], str] = {}     # (server, owner) -> the Swarm ticket from their sign-in

    @classmethod
    def open(cls, base: Config, spawn: Callable[[Callable[[], None]], None] | None = None,
             runner_class: type[JobRunner] = JobRunner) -> Registry:
        """The registry a server (or a command-line tool) opens on tortoise.yaml's data folder."""
        data = base.server.data_dir
        data.mkdir(parents=True, exist_ok=True)
        store = Store(data / "tortoise.db")
        ledger = Ledger(store, base.llm.budget, base.llm.request_log, base.llm.request_log_days)
        return cls(base, store, ledger, AiPool(base.llm.concurrency), make_llm(base), make_strong(base), spawn,
                   runner_class)

    @classmethod
    def single(cls, svc: Services, runner: JobRunner) -> Registry:
        """A registry around one bundle built on its own (tests): its workspace is the seed, attached as given, and
        keeps the bundle's own store keys."""
        ledger = svc.ledger if svc.ledger is not None else Ledger(svc.store, svc.cfg.llm.budget)
        reg = cls(svc.cfg, svc.store, ledger, runner.pool, svc.llm, svc.strong, spawn=lambda fn: fn(),
                  runner_class=type(runner))
        ws = reg._register_seed()
        ws.runner, ws.svc = runner, svc
        reg._check(ws)
        ws.loaded.set()
        return reg

    # ---- loading -------------------------------------------------------------------------
    def load(self) -> None:
        """Register the seed, then build every workspace's bundle in the background (§6)."""
        if self.base.workspace is not None:
            self._register_seed()
        rows = self.store.list_workspaces()
        if not rows:
            raise ConfigError(NO_WORKSPACE)
        for row in rows:
            ws = self._ws.get(row["id"]) or self._record(row)
            with self._lock:
                self._ws[ws.id] = ws
            self._start(ws)

    def _register_seed(self) -> Workspace:
        """The workspace tortoise.yaml describes, registered under its name and refreshed from the file at each start
        (§4); reviews made before workspaces become its own, and so do the single-workspace server's store entries
        (§12)."""
        cfg, ws = self.base, self.base.workspace
        name = seed_name(cfg)
        if not valid_name(name):
            raise ConfigError(f"workspace.name: {name!r} is not a workspace name (1–40 characters, no /)")
        fields = {"name": name, "vcs": ws.vcs, "p4port": ws.p4port, "client": ws.client, "p4user": cfg.owner,
                  "root": str(ws.root), "compile_commands": _stored(ws.compile_commands),
                  "build_root": str(ws.build_root) if ws.build_root is not None else None,
                  "swarm_url": cfg.swarm.url, "settings": ""}
        row = self.store.seed_workspace()
        clash = self._taken(name, str(ws.root), row["id"] if row else None)
        if clash:
            raise ConfigError(f"the workspace in tortoise.yaml: {clash}")
        if row is None:
            wid = self.store.add_workspace(fields, "config", cfg.owner)
            self._adopt_entries(wid)
        else:
            wid = row["id"]
            self.store.update_workspace(wid, fields)
        self.store.adopt_reviews(wid)
        rec = self._record(self.store.get_workspace(wid))
        with self._lock:
            self._ws[wid] = rec
        return rec

    def _adopt_entries(self, wid: int) -> None:
        """The single-workspace server's own entries, now the seed's: the owner's shared-sink marks and the flags
        libclang rejected (the layer model is rebuilt with the seed's index)."""
        scope = scope_of(wid)
        for old, new in ((MARKS_KEY, marks_key(scope)),
                         (strip_flags_key(self.base.workspace.root), strip_flags_key(self.base.workspace.root, scope))):
            got = self.store.kv_get(old)
            if got is not None and self.store.kv_get(new) is None:
                self.store.kv_put(new, got)

    def _record(self, row: dict) -> Workspace:
        """A stored workspace, with its effective configuration. Settings that no longer load leave it not ready, with
        the reason, until its owner edits them."""
        seed = row["source"] == "config" and self.base.workspace is not None
        reason = LOADING
        if seed:
            cfg = self.base
        else:
            try:
                cfg = effective_config(self.base, row)
            except ConfigError as e:
                try:
                    cfg = effective_config(self.base, {**row, "settings": ""})
                except ConfigError as e2:
                    raise ConfigError(f"the stored workspace {row['name']}: {e2}") from e2
                reason = f"its settings do not load: {e}"
        ws = Workspace(id=row["id"], name=row["name"], server=server_of(row["p4port"]), owner=row["p4user"],
                       seed=seed, cfg=cfg, reason=reason)
        if reason != LOADING:
            ws.loaded.set()                              # nothing to build until its owner edits it
        return ws

    def _start(self, ws: Workspace, wait: bool = False) -> None:
        if ws.reason != LOADING:
            return
        if wait:
            self._build(ws)
        else:
            self.spawn(lambda: self._build(ws))

    def settle(self, ws: Workspace, timeout: float = 120.0) -> None:
        """Wait while a workspace's bundle is still being built (right after startup), so a request then is answered
        once it has loaded rather than refused."""
        if ws.reason == LOADING:
            ws.loaded.wait(timeout)

    def _build(self, ws: Workspace) -> None:
        try:
            self._load(ws)
        finally:
            ws.loaded.set()

    def _load(self, ws: Workspace) -> None:
        """Build a workspace's bundle and start its queue; a failure keeps the workspace, not ready, with the reason
        (§11). An empty symbol index is built when the bundle first loads (§6)."""
        try:
            svc = build_services(ws.cfg, self.llm, strong=self.strong, store=self.store, ledger=self.ledger,
                                 home=self.home(ws.id), scope=scope_of(ws.id))
        except Exception as e:  # a missing root, an unreadable compile database: shown, never fatal
            ws.reason = f"could not load: {type(e).__name__}: {e}"
            log.warning("workspace %s: %s", ws.name, ws.reason)
            return
        runner = self.runner_class(svc, self.pool)
        with self._lock:
            if self._ws.get(ws.id) is not ws:            # removed or replaced while it was building
                return
            svc.owner_ticket = self._tickets.get((ws.server, ws.owner))
            runner.start()
            ws.runner, ws.svc = runner, svc
        if svc.index.generation() == 0:
            runner.submit_index()
        self._check(ws)

    def _check(self, ws: Workspace, report: HealthReport | None = None) -> HealthReport:
        """Its checks; the first failing hard check is why it isn't ready (§11)."""
        rep = report if report is not None else run_health(ws.svc)
        ws.checks = rep.checks
        bad = next((c for c in rep.checks if c.hard and not c.ok), None)
        ws.reason = f"{bad.name}: {bad.detail}" if bad else None
        return rep

    def recheck(self, ws: Workspace, deep: bool = False) -> HealthReport | None:
        """Its checks run again (its Health page); a bundle that failed to build is tried again first. None while it
        has no bundle."""
        self.settle(ws)
        if ws.svc is None and ws.reason is not None and ws.reason.startswith("could not load"):
            ws.reason = LOADING
            ws.loaded.clear()
            self._build(ws)
        if ws.svc is None:
            return None
        return self._check(ws, run_health(ws.svc, deep=deep))

    # ---- looking up ---------------------------------------------------------------------
    def all(self) -> list[Workspace]:
        with self._lock:                                 # requests add and remove workspaces meanwhile
            got = list(self._ws.values())
        return sorted(got, key=lambda w: w.name)

    def get(self, wid: int) -> Workspace | None:
        return self._ws.get(wid)

    def seed(self) -> Workspace | None:
        return next((w for w in self.all() if w.seed), None)

    def for_review(self, review: dict) -> Workspace | None:
        """A review's workspace; one made before workspaces belongs to the seed (§12)."""
        wid = review.get("workspace_id")
        return self.get(wid) if wid is not None else self.seed()

    def servers(self) -> list[str]:
        return sorted({w.server for w in self.all()})

    def owners(self, server: str) -> set[str]:
        return {w.owner for w in self.all() if w.server == server}

    def home(self, wid: int) -> Path:
        """A workspace's folder: its symbol index and toolchain files (§5)."""
        return self.base.server.data_dir / "workspaces" / str(wid)

    # ---- sign-in ------------------------------------------------------------------------
    def keep_ticket(self, server: str, user: str, ticket: str) -> None:
        """An owner's Swarm ticket, taken when they sign in to `server` (§7): for each workspace there they own, and
        for bundles built later."""
        with self._lock:                                 # a bundle attached meanwhile reads the ticket under it
            self._tickets[(server, user)] = ticket
            for w in self._ws.values():
                if w.server == server and w.owner == user and w.svc is not None:
                    w.svc.owner_ticket = ticket

    def login_runner(self, server: str) -> P4Runner | None:
        """What runs `p4 login` for `server`: from the root of one of its Perforce workspaces, so that folder's
        P4CONFIG settings (P4CHARSET, P4TRUST) apply; None when it has none (a git workspace's server, §5)."""
        ws = next((w for w in self.all() if w.server == server and w.cfg.workspace.vcs == "p4"), None)
        if ws is None:
            return None
        return P4Runner(server, None, ws.cfg.workspace.p4_bin, cwd=ws.cfg.workspace.root)

    # ---- adding, editing, removing (§8, §11) --------------------------------------------
    def add(self, fields: dict, by: str) -> Workspace:
        """Store a new workspace and build its bundle; it is saved even when its checks fail."""
        self._validate(fields, None)
        try:
            wid = self.store.add_workspace(fields, "ui", by)
        except sqlite3.IntegrityError as e:                  # added by someone else meanwhile
            raise Conflict(self._taken(fields["name"], fields["root"], None) or str(e)) from e
        ws = self._record(self.store.get_workspace(wid))
        with self._lock:
            self._ws[wid] = ws
        self._start(ws, wait=True)
        return ws

    def edit(self, wid: int, fields: dict) -> Workspace:
        """Store its new fields, build a new bundle and swap it in; refused while its queue has work (§6)."""
        old = self._editable(wid)
        self._idle(old)
        self._validate(fields, wid)
        try:
            self.store.update_workspace(wid, fields)
        except sqlite3.IntegrityError as e:
            raise Conflict(self._taken(fields["name"], fields["root"], wid) or str(e)) from e
        ws = self._record(self.store.get_workspace(wid))
        with self._lock:
            self._ws[wid] = ws
        if old.runner is not None:
            old.runner.stop()
        self._start(ws, wait=True)
        if ws.runner is not None:
            ws.runner.submit_index()                         # a new root or compile database: the index catches up
        return ws

    def remove(self, wid: int) -> None:
        """Forget a workspace with no reviews: its row, its folder and its store entries."""
        ws = self._editable(wid)
        n = self.store.review_count(wid)
        if n:
            raise Conflict(f"the workspace {ws.name} has {n} review(s); a workspace with reviews is kept")
        self._idle(ws)
        with self._lock:
            self._ws.pop(wid, None)
        if ws.runner is not None:
            ws.runner.stop()
        self.store.delete_workspace(wid)
        self.store.kv_delete_scope(scope_of(wid))
        shutil.rmtree(self.home(wid), ignore_errors=True)

    def _editable(self, wid: int) -> Workspace:
        ws = self.get(wid)
        if ws is None:
            raise KeyError(wid)
        if ws.seed:
            raise Conflict("set in tortoise.yaml")
        return ws

    @staticmethod
    def _idle(ws: Workspace) -> None:
        why = ws.runner.busy() if ws.runner is not None else None
        if why:
            raise Conflict(why)

    def _taken(self, name: str, root: str, wid: int | None) -> str | None:
        """Why another workspace already has this name, or this root however it is spelled; None when none has."""
        for row in self.store.list_workspaces():
            if row["id"] == wid:
                continue
            if row["name"] == name:
                return f"a workspace named {name} already exists"
            if canon(row["root"]) == canon(root):
                return f"the workspace {row['name']} already has the root {row['root']}"
        return None

    def _validate(self, fields: dict, wid: int | None) -> Config:
        """Its fields, checked before they are stored: Invalid for a bad value, Conflict for a name or root another
        workspace has."""
        if not valid_name(fields["name"]):
            raise Invalid("name: 1–40 characters, no /")
        if not os.path.isabs(fields["root"]):
            raise Invalid("root: a full path on this host")
        if not fields.get("p4user"):
            raise Invalid("user: the Perforce user its reads run as")
        if fields["vcs"] == "p4" and not (fields.get("p4port") and fields.get("client")):
            raise Invalid("a Perforce workspace needs its server (P4PORT) and its client")
        clash = self._taken(fields["name"], fields["root"], wid)
        if clash:
            raise Conflict(clash)
        try:
            return effective_config(self.base, fields)
        except ConfigError as e:
            raise Invalid(str(e)) from e

    # ---- command-line tools (§10) -------------------------------------------------------
    def tool_workspace(self, name: str | None = None) -> Workspace:
        """The workspace a command-line tool works on: the one named, else the seed, else the only one; its bundle
        built here, without a queue."""
        if self.base.workspace is not None:
            self._register_seed()
        rows = {r["name"]: r for r in self.store.list_workspaces()}
        if name is not None:
            row = rows.get(name)
            if row is None:
                raise ConfigError(f"no workspace named {name} (there are: {', '.join(sorted(rows)) or 'none'})")
        elif self.base.workspace is not None:
            row = self.store.seed_workspace()
        elif len(rows) == 1:
            [row] = rows.values()
        elif not rows:
            raise ConfigError(NO_WORKSPACE)
        else:
            raise ConfigError(f"several workspaces: name one with --workspace ({', '.join(sorted(rows))})")
        ws = self._record(row)
        if ws.reason != LOADING:
            raise ConfigError(f"the workspace {ws.name}: {ws.reason}")
        ws.svc = build_services(ws.cfg, self.llm, strong=self.strong, store=self.store, ledger=self.ledger,
                                home=self.home(ws.id), scope=scope_of(ws.id))
        ws.reason = None
        return ws
```

- [ ] **Step 4: Run the registry tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_workspaces.py -q`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd backend
git add codetortoise/workspaces.py tests/test_workspaces.py tests/conftest.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspaces): a registry of workspaces — the seed, stored ones, their bundles and queues; add, edit, remove

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: The web app on the registry — sign-in per server, access per review, owner rights per workspace

**Files:**
- Modify: `backend/codetortoise/store.py` (sessions)
- Modify: `backend/codetortoise/web/app.py`
- Modify: `backend/tests/helpers.py`
- Modify: `backend/tests/test_web.py`, `backend/tests/test_ondemand.py`, `backend/tests/test_tortoise.py`, `backend/tests/test_large_change.py`, `backend/tests/test_store.py`
- Create: `backend/tests/test_signin.py`

**Interfaces:**
- Consumes: Task 4's `Registry` (`single`, `all`, `get`, `for_review`, `servers`, `owners`, `keep_ticket`, `login_runner`, `settle`, `recheck`, `store`, `ledger`, `pool`, `base`), `Workspace` (`id`, `name`, `server`, `owner`, `cfg`, `svc`, `runner`, `reason`, `ready`); Task 3's `marks(store, scope)`, `set_mark(store, label, on, scope)`, `Services.scope`, `JobRunner.ai_jobs`.
- Produces:
  - `Store.open_session(ttl_days=7) -> str`; `Store.add_login(token, server, user)`; `Store.session_logins(token) -> dict[str, str] | None` (server → user; None without a live session); `Store.delete_session(token)` also drops its sign-ins. `create_session` and `session_user` are removed.
  - `create_app(reg: Registry, authenticate) -> FastAPI`, with `app.state.registry = reg`; `authenticate(server, user, password) -> str | None` (raises `LoginRejected`).
  - `make_authenticator(reg: Registry, runner_for: Callable[[str], P4Runner | None] | None = None)`.
  - HTTP (spec §8): `GET /api/servers` → `[{"server", "user"}]`; `POST /api/login` `{server?, user, password}` → `{"server", "user"}` (no `server`: allowed when there is one; else 422 `"choose a Perforce server"`); `GET /api/me` → `{"logins": [{"server", "user"}], "owner_of": [ids]}`; `GET /api/reviews` rows gain `workspace: {id, name, server}`; `POST /api/reviews` `{workspace_id?, cls, title?}` (no `workspace_id`: allowed when there is one workspace; else 422 `"choose a workspace"`); `GET /api/reviews/{id}` gains `workspace: {id, name, server}` and `viewer: {user, is_owner}`; a review on a server the session has no sign-in on answers 401 `{"detail": "sign in required", "server": "<server>"}`; `GET /api/workspaces/{id}/health`, `POST /api/workspaces/{id}/index/rebuild`, `GET /api/workspaces/{id}/sinks`, `PUT|DELETE /api/workspaces/{id}/sinks/{label}` replace `/api/health`, `/api/index/rebuild`, `/api/sinks…`.
  - `backend/tests/helpers.py`: `make_app(svc, runner, runner_for=None) -> FastAPI`.

- [ ] **Step 1: Write the failing store tests**

In `backend/tests/test_store.py`, add `import sqlite3` above `from datetime import UTC, datetime, timedelta` (if Task 2 has not already), and replace `test_sessions` with:

```python
def test_a_session_holds_one_sign_in_per_server(store):
    tok = store.open_session()
    assert store.session_logins(tok) == {}
    store.add_login(tok, "local", "amy")
    store.add_login(tok, "second:1666", "bob")
    store.add_login(tok, "local", "carol")                         # signing in there again replaces it
    assert store.session_logins(tok) == {"local": "carol", "second:1666": "bob"}
    assert store.session_logins("nope") is None and store.session_logins(None) is None
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    store._exec("UPDATE sessions SET expires_at=?", (past,))
    assert store.session_logins(tok) is None                       # expired
    tok2 = store.open_session()
    store.add_login(tok2, "local", "amy")
    store.delete_session(tok2)
    assert store.session_logins(tok2) is None
    assert store._all("SELECT * FROM session_logins WHERE server='local' AND user='amy'") == []


def test_sign_ins_from_before_per_server_sign_in_end(tmp_path):
    db = sqlite3.connect(tmp_path / "old.db")
    db.execute("CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user TEXT, created_at TEXT, expires_at TEXT)")
    db.execute("INSERT INTO sessions VALUES('h', 'amy', '2026-10-30', '2099-01-01')")
    db.commit()
    db.close()
    store = Store(tmp_path / "old.db")
    assert store._all("SELECT * FROM sessions") == []               # people sign in again (spec 2026-10-31 §12)
    tok = store.open_session()
    store.add_login(tok, "local", "amy")
    assert Store(tmp_path / "old.db").session_logins(tok) == {"local": "amy"}   # a later start keeps new ones
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_store.py -q`
Expected: FAIL with `AttributeError: 'Store' object has no attribute 'open_session'`.

- [ ] **Step 3: Implement the store's sign-ins**

In `backend/codetortoise/store.py`, `_SCHEMA` gains, after the `sessions` line:

```python
CREATE TABLE IF NOT EXISTS session_logins(token_hash TEXT, server TEXT, user TEXT, signed_in_at TEXT,
  PRIMARY KEY(token_hash, server));
```

In `Store.__init__`, inside `with self._lock:`, before `self._db.executescript(_SCHEMA)`:

```python
            had_logins = self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_logins'").fetchone() is not None
```

and after the `reviews.workspace_id` migration (Task 2):

```python
            if not had_logins:                       # sign-ins from before per-server sign-in end (spec 2026-10-31 §12)
                with self._db:
                    self._db.execute("DELETE FROM sessions")
```

Replace the sessions section (`create_session`, `session_user`, `delete_session`) with:

```python
    # ---- sessions: one sign-in per Perforce server (spec 2026-10-31 §5) ---------------
    def open_session(self, ttl_days: int = 7) -> str:
        """A browser session with no sign-in yet; its token is the cookie's value."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._exec("INSERT INTO sessions VALUES(?,?,?,?)",
                   (_hash(token), None, now.isoformat(), (now + timedelta(days=ttl_days)).isoformat()))
        return token

    def add_login(self, token: str, server: str, user: str) -> None:
        """The session's sign-in on `server`; signing in there again replaces it."""
        self._exec("INSERT OR REPLACE INTO session_logins VALUES(?,?,?,?)", (_hash(token), server, user, _now()))

    def session_logins(self, token: str | None) -> dict[str, str] | None:
        """server -> user for a live session; None without one (or when it has expired)."""
        if not token:
            return None
        rows = self._all("SELECT expires_at FROM sessions WHERE token_hash=?", (_hash(token),))
        if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
            return None
        got = self._all("SELECT server, user FROM session_logins WHERE token_hash=? ORDER BY server", (_hash(token),))
        return {r["server"]: r["user"] for r in got}

    def delete_session(self, token: str) -> None:
        self._exec("DELETE FROM session_logins WHERE token_hash=?", (_hash(token),))
        self._exec("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_store.py -q`
Expected: all pass. (The app still calls `create_session`; it is rewritten below in this task, so don't run the whole suite yet.)

- [ ] **Step 4: Write the failing app tests**

`backend/tests/helpers.py` gains:

```python
def make_app(svc, runner, runner_for=None):
    """The web app on a registry of one workspace: the bundle `svc` with its queue `runner`, as the seed."""
    from codetortoise.web.app import create_app, make_authenticator
    from codetortoise.workspaces import Registry
    reg = Registry.single(svc, runner)
    return create_app(reg, make_authenticator(reg, runner_for))
```

Switch every test app to it:

```bash
cd backend
sed -i -E 's/create_app\((\w+), (InlineRunner\(\w+\)|\w+), make_authenticator\(\w+\)\)/make_app(\1, \2)/' \
  tests/test_web.py tests/test_ondemand.py tests/test_tortoise.py tests/test_large_change.py
sed -i 's/^    from codetortoise.web.app import create_app, make_authenticator$/    from helpers import make_app/' \
  tests/test_large_change.py
```

then, by hand: in `tests/test_ondemand.py` and `tests/test_tortoise.py` change `from helpers import make_services` to `from helpers import make_app, make_services` and delete `from codetortoise.web.app import create_app, make_authenticator`; in `tests/test_web.py` the imports become

```python
import pytest
from fastapi.testclient import TestClient
from helpers import make_app, make_services

from codetortoise import boardstore
from codetortoise.pipeline import JobRunner, run_review
from codetortoise.web.app import make_authenticator
from codetortoise.workspaces import Registry
```

(keep any other imports the file has). `grep -n "create_app" tests/*.py` must now print only `tests/helpers.py`.

In `tests/test_ondemand.py`, the health call becomes `h = owner.get("/api/workspaces/1/health").json()`.

In `tests/test_web.py`:

```python
def test_auth_required_and_me(env):
    _, app, _ = env
    assert TestClient(app).get("/api/reviews").status_code == 401
    c = login(app, "owner")
    assert c.get("/api/me").json() == {"logins": [{"server": "local", "user": "owner"}], "owner_of": [1]}
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401


def test_health(env):
    svc, app, _ = env
    owner = login(app, "owner")
    svc.cfg.workspace.p4_sources = {"p4port": "P4CONFIG file /w/.p4config"}   # as load_config records it
    wid = owner.get("/api/me").json()["owner_of"][0]
    h = owner.get(f"/api/workspaces/{wid}/health").json()
    assert h["ready"] is True and h["index_building"] is False
    assert h["p4_sources"] == {"p4port": "P4CONFIG file /w/.p4config"}
    assert {c["name"] for c in h["checks"]} >= {"workspace root", "compile_commands", "libclang"}
    assert login(app, "bob").get(f"/api/workspaces/{wid}/health").status_code == 403
```

```python
def test_p4_authenticator_rejects_without_runner(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cfg.auth.mode = "p4"
    auth = make_authenticator(Registry.single(svc, InlineRunner(svc)))
    assert auth("local", "bob", "pw") is None                  # a git workspace's server: nothing checks the password


def test_owner_login_requests_host_unlocked_ticket_for_swarm(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cfg.auth.mode = "p4"
    calls = []

    class P4:
        def login_check(self, user, password, all_hosts=False):
            calls.append((user, all_hosts))
            return "TICKET"

    auth = make_authenticator(Registry.single(svc, InlineRunner(svc)), runner_for=lambda server: P4())
    assert auth("local", "owner", "pw") == "TICKET" and auth("local", "bob", "pw") == "TICKET"
    assert calls == [("owner", True), ("bob", False)]
```

In `test_expired_p4_password_is_explained_but_other_failures_stay_generic` replace the two lines `svc.p4 = P4()` and `app = make_app(svc, InlineRunner(svc))` (after the sed) with `app = make_app(svc, InlineRunner(svc), runner_for=lambda server: P4())`.

Replace `test_the_owner_marks_and_unmarks_shared_sinks_for_every_review` and `test_a_label_with_a_slash_or_percent_is_stored_as_given` with:

```python
SINKS = "/api/workspaces/1/sinks"


def test_the_owner_marks_and_unmarks_shared_sinks_for_every_review(env):
    svc, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    assert TestClient(app).get(SINKS).status_code == 401
    assert bob.get(SINKS).status_code == 403                       # the owner's (spec 2026-10-31 §7)
    assert owner.get(SINKS).json() == {"threshold": 20, "patterns": [], "marked": []}
    assert bob.put(f"{SINKS}/Uart%3A%3Aerrors").status_code == 403
    assert owner.put(f"{SINKS}/Uart%3A%3Aerrors").json()["marked"] == ["Uart::errors"]
    assert owner.put(f"{SINKS}/log_t%3A%3Abuf").json()["marked"] == ["Uart::errors", "log_t::buf"]
    assert bob.delete(f"{SINKS}/log_t%3A%3Abuf").status_code == 403
    assert owner.delete(f"{SINKS}/log_t%3A%3Abuf").json()["marked"] == ["Uart::errors"]
    assert svc.store.kv_get("sink_marks") == ["Uart::errors"]     # a bundle built on its own keeps its one entry
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    sinks = owner.get(f"/api/reviews/{rid}/reading").json()["sinks"]
    assert [(h["label"], h["why"]) for h in sinks] == [("Uart::errors", "marked")]
    assert any(f["sink"] for f in owner.get(f"/api/reviews/{rid}/findings").json())


def test_a_label_with_a_slash_or_percent_is_stored_as_given(env):
    _, app, _ = env
    owner = login(app, "owner")
    assert owner.put(f"{SINKS}/a%2Fb%3A%3Ac%25d").json()["marked"] == ["a/b::c%d"]
    assert owner.put(f"{SINKS}/" + "x" * 301).status_code == 422
```

Create `backend/tests/test_signin.py`:

```python
"""Sign-in per Perforce server, and what each sign-in sees and may do (spec 2026-10-31 §7, §8, §11)."""
import json

import pytest
from fastapi.testclient import TestClient
from helpers import make_app, make_services
from test_web import InlineRunner


@pytest.fixture
def two(fx, fx_b, tmp_path):
    """The fixture's workspace on `local` and a second, b, on second:1666 — both owned by a user named owner."""
    svc = make_services(fx, tmp_path)
    app = make_app(svc, InlineRunner(svc))
    reg = app.state.registry
    b = reg.add({"name": "b", "vcs": "git", "p4port": "second:1666", "client": None, "p4user": "owner",
                 "root": str(fx_b.root), "compile_commands": json.dumps("auto"), "build_root": None,
                 "swarm_url": None, "settings": ""}, "owner")
    assert b.ready
    return app, reg, b


def sign_in(client, server, user):
    r = client.post("/api/login", json={"server": server, "user": user, "password": "x"})
    assert r.status_code == 200 and r.json() == {"server": server, "user": user}, r.text
    return client


def test_one_session_signs_in_to_each_server(two):
    app, reg, b = two
    c = TestClient(app)
    assert c.get("/api/servers").json() == [{"server": "local", "user": None}, {"server": "second:1666", "user": None}]
    r = c.post("/api/login", json={"user": "amy", "password": "x"})
    assert r.status_code == 422 and r.json()["detail"] == "choose a Perforce server"
    assert c.post("/api/login", json={"server": "nowhere:1", "user": "amy", "password": "x"}).status_code == 422
    sign_in(c, "local", "amy")
    sign_in(c, "second:1666", "owner")
    assert c.get("/api/servers").json() == [{"server": "local", "user": "amy"},
                                            {"server": "second:1666", "user": "owner"}]
    assert c.get("/api/me").json() == {"logins": [{"server": "local", "user": "amy"},
                                                  {"server": "second:1666", "user": "owner"}], "owner_of": [b.id]}
    assert c.post("/api/reviews", json={"cls": [101]}).json()["detail"] == "choose a workspace"
    sign_in(c, "local", "owner")                                   # again on a server: replaces that sign-in
    assert c.get("/api/me").json()["owner_of"] == [1, b.id]
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401                     # sign out ends the whole session


def test_a_review_on_a_server_the_session_isnt_signed_in_to_is_hidden_and_names_its_server(two):
    app, reg, b = two
    both = sign_in(sign_in(TestClient(app), "local", "owner"), "second:1666", "owner")
    here = both.post("/api/reviews", json={"workspace_id": 1, "cls": [101]}).json()["id"]
    there = both.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    rows = {r["id"]: r["workspace"] for r in both.get("/api/reviews").json()}
    assert rows == {here: {"id": 1, "name": reg.get(1).name, "server": "local"},
                    there: {"id": b.id, "name": "b", "server": "second:1666"}}
    amy = sign_in(TestClient(app), "local", "amy")
    assert [r["id"] for r in amy.get("/api/reviews").json()] == [here]
    for path in ("", "/stories", "/reading", "/findings", "/comments", "/ai", "/files", "/names"):
        r = amy.get(f"/api/reviews/{there}{path}")
        assert r.status_code == 401 and r.json() == {"detail": "sign in required", "server": "second:1666"}, path
    comment = both.post(f"/api/reviews/{there}/comments", json={"body": "hi", "anchor_kind": "review"}).json()
    r = amy.delete(f"/api/comments/{comment['id']}")
    assert r.status_code == 401 and r.json()["server"] == "second:1666"
    assert amy.patch(f"/api/comments/{comment['id']}", json={"resolved": True}).status_code == 401
    assert amy.get("/api/reviews/999").status_code == 404
    d = amy.get(f"/api/reviews/{here}").json()
    assert d["workspace"] == {"id": 1, "name": reg.get(1).name, "server": "local"}
    assert d["viewer"] == {"user": "amy", "is_owner": False}
    assert both.get(f"/api/reviews/{there}").json()["viewer"] == {"user": "owner", "is_owner": True}


def test_owner_rights_follow_the_sign_in_on_the_workspaces_own_server(two):
    app, reg, b = two
    owner_b = sign_in(TestClient(app), "second:1666", "owner")
    rid = owner_b.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    c = sign_in(sign_in(TestClient(app), "local", "owner"), "second:1666", "mallory")   # owner here, mallory there
    assert c.get("/api/me").json()["owner_of"] == [1]
    assert c.get(f"/api/reviews/{rid}").json()["viewer"] == {"user": "mallory", "is_owner": False}
    for method, path, payload in (
            ("POST", "/api/reviews", {"workspace_id": b.id, "cls": [101]}),
            ("POST", f"/api/reviews/{rid}/rerun", None),
            ("PUT", f"/api/reviews/{rid}/ai/budget", {"budget": 5}),
            ("PUT", f"/api/reviews/{rid}/ai/rounds", {"rounds": 3}),
            ("PATCH", f"/api/reviews/{rid}/findings/F1", {"state": "ack"}),
            ("POST", f"/api/reviews/{rid}/cls/101/swarm/refresh", None),
            ("GET", f"/api/workspaces/{b.id}/health", None),
            ("POST", f"/api/workspaces/{b.id}/index/rebuild", None),
            ("GET", f"/api/workspaces/{b.id}/sinks", None),
            ("PUT", f"/api/workspaces/{b.id}/sinks/x%3A%3Ay", None)):
        r = c.request(method, path, json=payload)
        assert r.status_code == 403, (method, path, r.status_code)
    assert c.get("/api/workspaces/1/health").status_code == 200    # where they are the owner, they act as one


def test_a_workspace_that_isnt_ready_refuses_new_reviews_and_reruns_but_its_reviews_stay_readable(two):
    app, reg, b = two
    c = sign_in(TestClient(app), "second:1666", "owner")
    rid = c.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    b.reason = "compile_commands: no compile database found (auto)"          # its checks failed since
    r = c.post("/api/reviews", json={"workspace_id": b.id, "cls": [102]})
    assert r.status_code == 409 and r.json()["detail"] == (
        "the workspace b is not ready: compile_commands: no compile database found (auto); see its Health")
    assert c.post(f"/api/reviews/{rid}/rerun").status_code == 409
    assert c.get(f"/api/reviews/{rid}/stories").status_code == 200
```

- [ ] **Step 5: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_signin.py tests/test_web.py -q -x 2>&1 | tail -5`
Expected: FAIL — `create_app` still takes `(svc, runner, authenticate)`: `AttributeError: 'Registry' object has no attribute 'store'`-style errors or `TypeError: create_app() missing 1 required positional argument: 'authenticate'`.

- [ ] **Step 6: Rewrite the app's top half**

In `backend/codetortoise/web/app.py`:

Imports: add `from collections.abc import Callable` and `from dataclasses import dataclass`; `from fastapi.responses import FileResponse, JSONResponse, StreamingResponse`; replace `from codetortoise.health import run_health` with `from codetortoise.health import HealthReport`; delete `from codetortoise.pipeline import JobRunner`; add `from codetortoise.vcs.p4runner import P4Error, P4Runner` (replacing the `P4Error` import) and `from codetortoise.workspaces import Registry, Workspace`. Keep `from codetortoise.services import Services` (used by `bundle`).

`LoginIn` and `ReviewIn` become:

```python
class LoginIn(BaseModel):
    server: str | None = None        # the Perforce server to sign in to (spec 2026-10-31 §7); may be left out with one
    user: str
    password: str = ""


class ReviewIn(BaseModel):
    workspace_id: int | None = None  # may be left out on a server of one workspace
    cls: list[int] = Field(min_length=1)
    title: str | None = None
```

After `RERUNNING = …` add:

```python
class SignInRequired(Exception):
    """A review on a Perforce server the session has no sign-in on (spec 2026-10-31 §7): 401 naming the server, so the
    UI can offer that server's sign-in."""

    def __init__(self, server: str):
        super().__init__(server)
        self.server = server


@dataclass
class Access:
    """A review, its workspace and the session's sign-in on that workspace's server: who acts inside it (§7)."""
    review: dict
    ws: Workspace
    user: str

    @property
    def rid(self) -> int:
        return self.review["id"]

    @property
    def is_owner(self) -> bool:
        return self.user == self.ws.owner


@dataclass
class Owned:
    """A workspace, acted on by its owner (§7)."""
    ws: Workspace
    user: str
    logins: dict[str, str]
```

Replace `create_app`'s head — from its `def` line through `review_or_404` — with:

```python
def create_app(reg: Registry, authenticate) -> FastAPI:
    """authenticate(server, user, password) -> ticket str on success, None on failure."""
    app = FastAPI(title="CodeTortoise")
    app.state.registry = reg
    store = reg.store
    # work a stopped server left unfinished: answers can't resume, so end them (spec 2026-10-03 §5); once per server
    store.end_pending_ai_replies("I couldn't answer: CodeTortoise restarted before the answer was finished. Ask again.")
    reg.ledger.fail_running()
    reg.ledger.prune()                         # logged requests past llm.request_log_days

    @app.exception_handler(SignInRequired)
    async def sign_in_required(request: Request, e: SignInRequired):
        return JSONResponse({"detail": "sign in required", "server": e.server}, status_code=401)

    def logins_of(request: Request) -> dict[str, str]:
        """The session's sign-ins, server -> user."""
        got = store.session_logins(request.cookies.get(COOKIE))
        if not got:
            raise HTTPException(401, "login required")
        return got

    def in_review(rid: int, logins: dict[str, str] = Depends(logins_of)) -> Access:
        """The review, read as the session's sign-in on its workspace's server (§7)."""
        r = store.get_review(rid)
        ws = reg.for_review(r) if r is not None else None
        if ws is None:
            raise HTTPException(404, "review not found")
        user = logins.get(ws.server)
        if user is None:
            raise SignInRequired(ws.server)
        return Access(r, ws, user)

    def owner_in_review(a: Access = Depends(in_review)) -> Access:
        if not a.is_owner:
            raise HTTPException(403, "owner only")
        return a

    def owned(wid: int, logins: dict[str, str] = Depends(logins_of)) -> Owned:
        """A workspace its owner acts on: 404 off the session's servers, 403 for anyone else (§7)."""
        ws = reg.get(wid)
        if ws is None or ws.server not in logins:
            raise HTTPException(404, "workspace not found")
        if logins[ws.server] != ws.owner:
            raise HTTPException(403, "owner only")
        return Owned(ws, logins[ws.server], logins)

    def bundle(ws: Workspace) -> Services:
        """A workspace's bundle (waited for while it is still being built, right after startup); 409 with the reason
        while it has none."""
        reg.settle(ws)
        if ws.svc is None:
            raise HTTPException(409, f"the workspace {ws.name} is not loaded: {ws.reason}")
        return ws.svc

    def ready(ws: Workspace) -> Services:
        """A workspace's bundle when its checks pass; 409 with the reason otherwise (§11)."""
        reg.settle(ws)
        if not ws.ready:
            raise HTTPException(409, f"the workspace {ws.name} is not ready: {ws.reason}; see its Health")
        return ws.svc

    def ws_ref(ws: Workspace) -> dict:
        return {"id": ws.id, "name": ws.name, "server": ws.server}
```

Replace the auth section and `/api/me` with:

```python
    # ---- sign-in: one per Perforce server (spec 2026-10-31 §7) ----------------------
    @app.get("/api/servers")
    def servers(request: Request):
        """The Perforce servers of all workspaces, each with the session's user there or null; open to the sign-in
        page."""
        logins = store.session_logins(request.cookies.get(COOKIE)) or {}
        return [{"server": s, "user": logins.get(s)} for s in reg.servers()]

    @app.post("/api/login")
    def login(body: LoginIn, request: Request, response: Response):
        known = reg.servers()
        server = body.server if body.server is not None else (known[0] if len(known) == 1 else None)
        if server is None:
            raise HTTPException(422, "choose a Perforce server")
        if server not in known:
            raise HTTPException(422, f"no workspace is on {server}")
        try:
            ticket = authenticate(server, body.user, body.password)
        except LoginRejected as e:
            raise HTTPException(401, str(e)) from e
        if ticket is None:
            raise HTTPException(401, "invalid credentials")
        if body.user in reg.owners(server):
            reg.keep_ticket(server, body.user, ticket)
        token = request.cookies.get(COOKIE)
        if store.session_logins(token) is None:
            token = store.open_session()
        store.add_login(token, server, body.user)
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400,
                            secure=reg.base.server.tls_cert is not None)
        return {"server": server, "user": body.user}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            store.delete_session(tok)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(logins: dict[str, str] = Depends(logins_of)):
        """The session's sign-ins and the workspaces it owns (§8)."""
        return {"logins": [{"server": s, "user": u} for s, u in sorted(logins.items())],
                "owner_of": sorted(w.id for w in reg.all() if logins.get(w.server) == w.owner)}

    # ---- a workspace's health, index and shared sinks (owner; spec 2026-10-31 §8) -----
    @app.get("/api/workspaces/{wid}/health")
    def health(o: Owned = Depends(owned)):
        """Its checks run again, with a sample parse per toolchain group (its Health page)."""
        rep = reg.recheck(o.ws, deep=True)
        if rep is None:                              # no bundle: what stops it is the one check shown
            rep = HealthReport(checks=[{"name": "workspace", "ok": False, "hard": True, "detail": o.ws.reason or ""}],
                               ready=False)
        return {**rep.model_dump(), "index_building": o.ws.runner.index_building if o.ws.runner else False}

    @app.post("/api/workspaces/{wid}/index/rebuild")
    def rebuild_index(o: Owned = Depends(owned)):
        bundle(o.ws)
        o.ws.runner.submit_index()
        return {"queued": True}
```

Delete the old `/api/health` and `/api/index/rebuild` handlers. Replace `list_reviews`, `create_review`, `get_review` and `rerun` with:

```python
    @app.get("/api/reviews")
    def list_reviews(logins: dict[str, str] = Depends(logins_of)):
        """The reviews on the session's servers, each with its workspace (§8)."""
        out = []
        for r in store.list_reviews():
            ws = reg.for_review(r)
            if ws is None or ws.server not in logins:
                continue
            r["workspace"] = ws_ref(ws)
            r["headline"] = review_headline(r["id"])
            out.append(r)
        return out

    @app.post("/api/reviews")
    def create_review(body: ReviewIn, logins: dict[str, str] = Depends(logins_of)):
        """A review in a workspace, by its owner; refused while the workspace isn't ready (§8, §11)."""
        wid = body.workspace_id
        if wid is None:
            every = reg.all()
            if len(every) != 1:
                raise HTTPException(422, "choose a workspace")
            wid = every[0].id
        o = owned(wid, logins)
        ready(o.ws)
        title = body.title or "CLs " + ", ".join(str(c) for c in sorted(set(body.cls)))
        rid = store.create_review(title, o.user, body.cls, workspace_id=o.ws.id)
        o.ws.runner.submit_review(rid)
        return store.get_review(rid)

    @app.get("/api/reviews/{rid}")
    def get_review(rid: int, a: Access = Depends(in_review)):
        """The review, its CLs and stages, its workspace, and who the session is inside it (§8)."""
        return {"review": a.review, "cls": store.list_cls(rid), "stages": store.list_stages(rid),
                "workspace": ws_ref(a.ws), "viewer": {"user": a.user, "is_owner": a.is_owner}}

    @app.post("/api/reviews/{rid}/rerun")
    def rerun(rid: int, fresh: bool = False, a: Access = Depends(owner_in_review)):
        """Run the review again; `fresh` asks the strong model for new stories instead of reusing a brief. Refused while
        its workspace isn't ready (§11)."""
        ready(a.ws)
        a.ws.runner.submit_review(rid, fresh=fresh)
        return {"queued": True}
```

- [ ] **Step 7: Move every review path onto `Access`**

Two rules for the remaining handlers under `/api/reviews/{rid}/…`:

- **Rule A** — a handler taking `_: str = Depends(user_of)` or `user: str = Depends(user_of)`: that parameter becomes `a: Access = Depends(in_review)`; delete its `review_or_404(rid)` line; in its body `user` becomes `a.user`.
- **Rule B** — a handler taking `_: str = Depends(owner_of)` or `user: str = Depends(owner_of)`: that parameter becomes `a: Access = Depends(owner_in_review)`; delete its `review_or_404(rid)` line if it has one; `user` becomes `a.user`.

Rule A alone: `events`, `overview`, `board`, `stories`, `story`, `reading`, `mark_checks`, `unmark_checks`, `mark_check`, `unmark_check`, `ticks`, `tick`, `untick`, `locate`, `node_names`, `files`, `changed_file`, `ai_requests`, `comments`. Rule B alone: `finding_state`.

These get Rule A or B plus a new body — replace them whole:

```python
    @app.get("/api/reviews/{rid}/nodes/{nid}/neighbours")
    def node_neighbours(rid: int, nid: str, limit: int = 20, callers: int | None = None, callees: int | None = None,
                        a: Access = Depends(in_review)):
        """A node's callers and callees, the most affected first (spec 2026-10-04-review-workspace §4.3)."""
        im, depot_of, ss = shown(rid)
        out = neighbours(im, nid, depot_of, ss.node_story if ss else {}, root=canon(str(a.ws.cfg.workspace.root)),
                         limit=limit, callers=callers, callees=callees)
        if out is None:
            raise HTTPException(404, f"no node {nid} in this review")
        return out

    @app.get("/api/reviews/{rid}/source")
    def source(rid: int, path: str, side: Literal["before", "after"] = "after", a: Access = Depends(in_review)):
        """A file's text for the board: changed files from the change set, others from the base workspace."""
        f = filestore.one(store, rid, path)
        if f is not None:
            rev = (f.get("base_rev") or "base") if side == "before" else "changed"
            return {"path": path, "depot": path, "rev": rev, "text": f[side], "changed": True}
        key = f"source:{path}"
        cached = store.get_blob(rid, key)
        if cached is None:
            try:
                sf = bundle(a.ws).source.read(path)
            except SourceNotAllowed as e:
                raise HTTPException(403, str(e)) from e
            except SourceBinary as e:
                raise HTTPException(415, str(e)) from e
            except SourceTooLarge as e:
                raise HTTPException(413, str(e)) from e
            except P4Error as e:
                raise HTTPException(502, f"Perforce: {e}") from e
            cached = {"path": path, "depot": sf.depot, "rev": sf.rev, "text": sf.text, "changed": False}
            store.put_blob(rid, key, cached)
        return cached

    @app.get("/api/reviews/{rid}/findings")
    def findings(rid: int, a: Access = Depends(in_review)):
        root = canon(str(a.ws.cfg.workspace.root))               # text read by people; titles stay as stored (anchors)
        return [f.model_copy(update={"summary": tidy(f.summary, root),
                                     "evidence": [e.model_copy(update={"text": tidy(e.text, root)}) for e in f.evidence]})
                .model_dump() for f in store.list_findings(rid)]
```

Replace the `# ---- shared sinks` section (its helpers and three handlers) with:

```python
    # ---- shared sinks (spec 2026-10-09-shared-sinks §6), per workspace (spec 2026-10-31 §5) ----
    def sinks_view(ws: Workspace) -> dict:
        an = ws.cfg.analysis
        return {"threshold": an.sink_threshold, "patterns": an.sink_fields, "marked": marks(store, bundle(ws).scope)}

    def sink_label(label: str) -> str:
        if not label.strip() or len(label) > 300:
            raise HTTPException(422, "a field's label, as record::field")
        return label

    @app.get("/api/workspaces/{wid}/sinks")
    def sinks(o: Owned = Depends(owned)):
        return sinks_view(o.ws)

    @app.put("/api/workspaces/{wid}/sinks/{label:path}")
    def mark_sink(label: str, o: Owned = Depends(owned)):
        set_mark(store, sink_label(label), True, bundle(o.ws).scope)
        return sinks_view(o.ws)

    @app.delete("/api/workspaces/{wid}/sinks/{label:path}")
    def unmark_sink(label: str, o: Owned = Depends(owned)):
        set_mark(store, sink_label(label), False, bundle(o.ws).scope)
        return sinks_view(o.ws)
```

Replace `explain`, `ai_view`, `ai_calls`, `ai_budget`, `ai_rounds`:

```python
    @app.post("/api/reviews/{rid}/explain", status_code=202)
    def explain(rid: int, body: ExplainIn, a: Access = Depends(in_review)):
        svc = bundle(a.ws)
        if svc.llm is None or svc.ledger is None:
            raise HTTPException(409, "no LLM is configured")
        if a.review["status"] not in TERMINAL:
            raise HTTPException(409, RERUNNING)
        try:
            ondemand.check_target(svc, rid, body.kind, body.target)
        except ondemand.NotFound as e:
            raise HTTPException(404, str(e)) from e
        same = next((j for j in reg.pool.jobs.get(rid, []) if j["status"] == "running" and j["kind"] == body.kind
                     and j["target"] == body.target), None)
        if same:                                       # someone is already asking: share that answer, pay once
            return same
        reason = svc.ledger.check(rid, a.user)
        if reason:
            raise HTTPException(429, reason)
        return a.ws.runner.submit_ai(rid, a.user, body.kind, body.target,
                                     lambda: ondemand.explain(svc, rid, a.user, body.kind, body.target))

    @app.get("/api/reviews/{rid}/ai")
    def ai_view(rid: int, a: Access = Depends(in_review)):
        svc, cfg, ledger = a.ws.svc, a.ws.cfg, reg.ledger
        b = cfg.llm.budget
        u = ledger.usage(rid)
        u.pop("calls", None)                           # polled while work is pending; the list is /ai/calls
        strong = cfg.llm.strong.model if svc is not None and svc.strong is not None and cfg.llm.strong else None
        return {**u, "llm": svc is not None and svc.llm is not None, "strong": strong,
                "me_today": ledger.person_today(a.user), "me_limit": b.per_person_daily,
                "per_mention": ledger.rounds(rid), "is_owner": a.is_owner, "jobs": reg.pool.jobs.get(rid, []),
                "file_summaries": store.get_blob(rid, "file_summaries") or {}}

    @app.get("/api/reviews/{rid}/ai/calls")
    def ai_calls(rid: int, a: Access = Depends(in_review)):
        return reg.ledger.usage(rid)["calls"]
```

```python
    @app.put("/api/reviews/{rid}/ai/budget")
    def ai_budget(rid: int, body: BudgetIn, a: Access = Depends(owner_in_review)):
        reg.ledger.raise_budget(rid, body.budget, a.user)
        return {"budget": reg.ledger.budget(rid)}

    @app.put("/api/reviews/{rid}/ai/rounds")
    def ai_rounds(rid: int, body: RoundsIn, a: Access = Depends(owner_in_review)):
        reg.ledger.set_rounds(rid, body.rounds, a.user)
        return {"rounds": reg.ledger.rounds(rid)}
```

Replace `add_comment`, `ask_tortoise`, `edit_comment`, `delete_comment`:

```python
    @app.post("/api/reviews/{rid}/comments")
    def add_comment(rid: int, body: CommentIn, a: Access = Depends(in_review)):
        if body.parent_id is not None:
            parent = store.get_comment(body.parent_id)
            if parent is None or parent["review_id"] != rid:
                raise HTTPException(400, "bad parent_id")
        c = store.add_comment(rid, a.user, body.body, body.anchor_kind, body.anchor, body.parent_id)
        if tortoise.mentions(body.body) and a.user != tortoise.AUTHOR:
            ask_tortoise(a, c)
        return c

    def ask_tortoise(a: Access, question: dict) -> None:
        """Post tortoise's reply in the question's thread and answer it as a job (spec 2026-10-03 §5)."""
        rid, user, svc = a.rid, a.user, a.ws.svc
        root = question["parent_id"] or question["id"]
        reply = store.add_comment(rid, tortoise.AUTHOR, "thinking…", question["anchor_kind"], question["anchor"], root)
        base = {"pending": False, "read": [], "files": [], "calls": 0}
        if svc is None:
            why = f"the workspace {a.ws.name} is not loaded: {a.ws.reason}"
            store.set_ai_reply(reply["id"], f"I can't answer: {why}.", {**base, "error": why})
            return
        if svc.llm is None or svc.ledger is None:
            store.set_ai_reply(reply["id"], "I can't answer: no AI is configured for CodeTortoise.",
                               {**base, "error": "no LLM"})
            return
        reason = svc.ledger.check(rid, user)
        if reason:
            store.set_ai_reply(reply["id"], f"I couldn't answer: {reason}.", {**base, "error": reason})
            return
        if store.get_review(rid)["status"] not in TERMINAL:
            store.set_ai_reply(reply["id"], f"I couldn't answer: {RERUNNING}. Ask again when it finishes.",
                               {**base, "error": RERUNNING})
            return
        store.set_ai_reply(reply["id"], "thinking…", {**base, "pending": True, "round": 0,
                                                      "of": svc.ledger.rounds(rid)})
        a.ws.runner.submit_ai(rid, user, "mention", str(reply["id"]),
                              lambda: tortoise.answer(svc, rid, user, question, reply["id"]))

    def comment_access(cid: int, logins: dict[str, str] = Depends(logins_of)) -> tuple[dict, Access]:
        """A comment and its review, read as the session's sign-in on that review's server."""
        c = store.get_comment(cid)
        if c is None:
            raise HTTPException(404, "comment not found")
        return c, in_review(c["review_id"], logins)

    @app.patch("/api/comments/{cid}")
    def edit_comment(cid: int, body: CommentPatch, got: tuple[dict, Access] = Depends(comment_access)):
        c, a = got
        if body.body is not None and c["author"] != a.user:
            raise HTTPException(403, "only the author can edit")
        return store.update_comment(cid, body=body.body, resolved=body.resolved)

    @app.delete("/api/comments/{cid}")
    def delete_comment(cid: int, got: tuple[dict, Access] = Depends(comment_access)):
        c, a = got
        if c["author"] != a.user and not a.is_owner:
            raise HTTPException(403, "only the author or owner can delete")
        store.delete_comment(cid)
        return {"ok": True}
```

Replace the Swarm section's `swarm_client` and its three handlers:

```python
    def swarm_client(a: Access):
        client = bundle(a.ws).swarm()
        if client is None:
            raise HTTPException(409, "Swarm not configured or owner not logged in")
        return client

    def cl_row(rid: int, cl: int) -> dict:
        row = next((c for c in store.list_cls(rid) if c["cl"] == cl), None)
        if row is None:
            raise HTTPException(404, "CL not in review")
        return row

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/refresh")
    def swarm_refresh(rid: int, cl: int, a: Access = Depends(owner_in_review)):
        cl_row(rid, cl)
        try:
            data = swarm_client(a).get_review_for_change(cl)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/create")
    def swarm_create(rid: int, cl: int, a: Access = Depends(owner_in_review)):
        row = cl_row(rid, cl)
        if row["status"] != "pending":
            raise HTTPException(409, "only pending (shelved) CLs can get a new Swarm review")
        if row.get("swarm"):
            raise HTTPException(409, "CL already has a Swarm review")
        try:
            data = swarm_client(a).create_review(cl, row.get("description") or f"CL {cl}")
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        store.record_swarm_post(rid, cl, "create", str(data.get("id")))
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/post")
    def swarm_post(rid: int, cl: int, body: SwarmPostIn, a: Access = Depends(owner_in_review)):
        row = cl_row(rid, cl)
        if not row.get("swarm"):
            raise HTTPException(409, "CL has no Swarm review")
        if any(p["kind"] == "summary" for p in store.swarm_posts(rid, cl)) and not body.confirm_repeat:
            raise HTTPException(409, "summary already posted; resend with confirm_repeat")
        sb = store.get_blob(rid, "storyboard") or {}
        link = f"{reg.base.server.public_url.rstrip('/')}/r/{rid}"
        text = f"CodeTortoise review (risk: {sb.get('risk', 'n/a')}): {sb.get('summary', '')}\n\nFull storyboard: {link}"
        try:
            cid = swarm_client(a).post_comment(row["swarm"]["id"], text)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.record_swarm_post(rid, cl, "summary", cid)
        return {"comment_id": cid}
```

Replace `make_authenticator`:

```python
def make_authenticator(reg: Registry, runner_for: Callable[[str], P4Runner | None] | None = None):
    """authenticate(server, user, password) -> a ticket, or None. `runner_for(server)` is what runs `p4 login` there
    (default: the registry's, from one of that server's Perforce workspaces; none for a git workspace's server)."""
    if reg.base.auth.mode == "dev":
        return lambda server, user, password: "" if user else None
    runner_for = runner_for or reg.login_runner

    def p4_auth(server: str, user: str, password: str) -> str | None:
        p4 = runner_for(server)
        if p4 is None or not user:
            return None
        try:
            return p4.login_check(user, password, all_hosts=user in reg.owners(server))
        except P4Error as e:
            if "expired" in str(e).lower():
                raise LoginRejected("Your Perforce password has expired. Change it with `p4 passwd`, then sign in "
                                    "again.") from e
            return None
    return p4_auth
```

Then check nothing of the old single bundle is left inside `create_app`:

Run: `cd backend && grep -nE "user_of|owner_of|review_or_404|state\[" codetortoise/web/app.py; .venv/bin/ruff check codetortoise/web/app.py`
Expected: grep prints nothing; ruff is clean — an `F821 Undefined name` for `svc`, `cfg` or `runner` marks a handler still using the old single bundle (`svc` → `bundle(a.ws)` or `a.ws.svc`, `cfg` → `a.ws.cfg` or `reg.base`, `runner` → `a.ws.runner`).

- [ ] **Step 8: Run the app tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_signin.py tests/test_web.py tests/test_ondemand.py tests/test_tortoise.py tests/test_large_change.py tests/test_store.py -q 2>&1 | tail -5`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff clean.

Do not run the end-to-end suite in this task: the UI still calls `/api/health`, `/api/sinks` and reads the old `/api/me`
until Task 8, which moves it to these endpoints and runs the whole suite.

- [ ] **Step 9: Commit**

```bash
cd backend
git add codetortoise/store.py codetortoise/web/app.py tests/helpers.py tests/test_web.py tests/test_ondemand.py \
  tests/test_tortoise.py tests/test_large_change.py tests/test_store.py tests/test_signin.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(web): the app on the registry — sign-in per Perforce server, reviews by server, owner rights per workspace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 6: The workspaces API — list, add, detect, edit, remove

**Files:**
- Modify: `backend/codetortoise/web/app.py`
- Create: `backend/tests/test_workspace_api.py`

**Interfaces:**
- Consumes: Task 4's `Registry.add/edit/remove`, `Conflict`, `Invalid`, `server_of`; Task 5's `logins_of`, `owned`, `Owned`, `bundle`; `codetortoise.init_config.scan`.
- Produces (spec §8):
  - `GET /api/workspaces` → rows `{id, name, server, client, vcs, ready, reason, seed, is_owner}`, plus `fields: {name, vcs, p4port, client, p4user, root, compile_commands, build_root, swarm_url, settings}` for the owner (`compile_commands` as text: `auto`, a path, or one path per line).
  - `POST /api/workspaces` (body `WorkspaceIn`) → the row plus `checks: [{name, ok, hard, detail}]`; 403 `"only the owner of a workspace adds workspaces"`, 409 (name or root taken), 422 (a bad value).
  - `POST /api/workspaces/detect` `{root}` → `{root, p4port, client, p4user, compile_commands: [paths], client_root, notes: [text]}`.
  - `PUT /api/workspaces/{id}` (body `WorkspaceIn`) → row plus `checks`; `DELETE /api/workspaces/{id}` → `{"ok": true}`; both 409 `"set in tortoise.yaml"` for the seed.
  - `WorkspaceIn` JSON: `{name, vcs ("p4"|"git"), p4port?, client?, p4user, root, compile_commands (default "auto"), build_root?, swarm_url?, settings (default "")}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_workspace_api.py`:

```python
"""The Workspaces page's API (spec 2026-10-31 §8, §9, §11)."""
import json

import pytest
from helpers import make_app, make_services
from test_web import InlineRunner, login


@pytest.fixture
def app(fx, tmp_path):
    svc = make_services(fx, tmp_path / "data")
    return make_app(svc, InlineRunner(svc))


def body(root, name="b", **kw):
    return {"name": name, "vcs": "git", "p4user": "owner", "root": str(root), **kw}


def test_an_owner_adds_checks_edits_and_removes_a_workspace(app, fx, fx_b, tmp_path):
    owner, bob = login(app, "owner"), login(app, "bob")
    r = bob.post("/api/workspaces", json=body(fx_b.root))
    assert r.status_code == 403 and r.json()["detail"] == "only the owner of a workspace adds workspaces"
    r = owner.post("/api/workspaces", json=body(f"{fx_b.root}/"))
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["name"], b["server"], b["ready"], b["seed"], b["is_owner"]) == ("b", "local", True, False, True)
    assert b["fields"]["root"] == str(fx_b.root) and b["fields"]["compile_commands"] == "auto"   # stored normalised
    assert {c["name"] for c in b["checks"]} >= {"workspace root", "compile_commands", "libclang"}
    assert owner.post("/api/workspaces", json=body(fx_b.root, name="again")).status_code == 409
    assert owner.post("/api/workspaces", json=body(fx_b.root, name="a/b")).status_code == 422
    r = owner.post("/api/workspaces", json=body(tmp_path, name="x", settings="server: {}"))
    assert r.status_code == 422 and "only toolchain, targets and analysis" in r.json()["detail"]
    assert [(w["name"], w["seed"]) for w in owner.get("/api/workspaces").json()] == [("b", False), (fx.root.name, True)]
    assert all("fields" not in w for w in bob.get("/api/workspaces").json())   # only owners get the settings
    assert owner.put("/api/workspaces/1", json=body(fx.root, name="x")).json()["detail"] == "set in tortoise.yaml"
    assert owner.delete("/api/workspaces/1").json()["detail"] == "set in tortoise.yaml"
    assert bob.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root)).status_code == 403
    e = owner.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, settings="analysis: {sink_threshold: 3}",
                                                       compile_commands=f"{fx_b.root}/compile_commands.json"))
    assert e.status_code == 200, e.text
    assert e.json()["fields"]["settings"] == "analysis: {sink_threshold: 3}"
    assert e.json()["fields"]["compile_commands"] == f"{fx_b.root}/compile_commands.json"
    assert owner.get(f"/api/workspaces/{b['id']}/sinks").json()["threshold"] == 3     # its own analysis settings
    assert owner.get("/api/workspaces/1/sinks").json()["threshold"] == 20
    assert owner.delete(f"/api/workspaces/{b['id']}").json() == {"ok": True}
    assert [w["name"] for w in owner.get("/api/workspaces").json()] == [fx.root.name]


def test_a_workspace_on_another_server_is_listed_to_those_signed_in_there(app, fx_b):
    owner = login(app, "owner")
    assert owner.post("/api/workspaces", json=body(fx_b.root, p4port="second:1666")).status_code == 200
    assert [w["server"] for w in owner.get("/api/workspaces").json()] == ["local"]
    owner.post("/api/login", json={"server": "second:1666", "user": "owner", "password": "x"})
    assert [w["server"] for w in owner.get("/api/workspaces").json()] == ["second:1666", "local"]


def test_detect_fills_the_add_form_from_what_is_at_a_root(app, tmp_path, monkeypatch):
    owner = login(app, "owner")
    root = tmp_path / "w"
    (root / "build").mkdir(parents=True)
    (root / "build" / "compile_commands.json").write_text(
        json.dumps([{"directory": str(root), "file": "a.c", "arguments": ["cc", "-c", "a.c"]}]))
    (root / ".p4config").write_text("P4PORT=p4.invalid:1666\nP4CLIENT=amy-w\nP4USER=amy\n")
    monkeypatch.setenv("P4CONFIG", ".p4config")
    d = owner.post("/api/workspaces/detect", json={"root": str(root)}).json()
    assert (d["root"], d["p4port"], d["client"], d["p4user"]) == (str(root.resolve()), "p4.invalid:1666", "amy-w", "amy")
    assert d["compile_commands"] == [str((root / "build" / "compile_commands.json").resolve())]
    assert any("p4 client -o amy-w" in n for n in d["notes"])      # no Perforce here: said, not fatal
    assert owner.post("/api/workspaces/detect", json={"root": "w"}).status_code == 422
    assert login(app, "bob").post("/api/workspaces/detect", json={"root": str(root)}).status_code == 403
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_workspace_api.py -q`
Expected: FAIL — `POST /api/workspaces` answers 405 (only `/api/workspaces/{wid}/…` routes exist), so the first status assertion fails.

- [ ] **Step 3: Implement**

In `backend/codetortoise/web/app.py` add `import os` to the imports, `from codetortoise.init_config import scan`, and extend the workspaces import to `from codetortoise.workspaces import Conflict, Invalid, Registry, Workspace`. After `KeysIn` add:

```python
class WorkspaceIn(BaseModel):
    """A workspace as the Workspaces page sends it (spec 2026-10-31 §9)."""
    name: str
    vcs: Literal["p4", "git"] = "p4"
    p4port: str | None = None
    client: str | None = None
    p4user: str
    root: str
    compile_commands: str = "auto"       # "auto", a path, or several (one per line)
    build_root: str | None = None
    swarm_url: str | None = None
    settings: str = ""                   # YAML: tortoise.yaml's toolchain, targets and analysis keys

    def fields(self) -> dict:
        """The workspaces table's columns: blanks unset, the root normalised, the compile database as JSON."""
        def opt(v: str | None) -> str | None:
            return (v.strip() or None) if v is not None else None
        paths = [line.strip() for line in self.compile_commands.splitlines() if line.strip()]
        cc = "auto" if paths in ([], ["auto"]) else paths[0] if len(paths) == 1 else paths
        return {"name": self.name.strip(), "vcs": self.vcs, "p4port": opt(self.p4port), "client": opt(self.client),
                "p4user": self.p4user.strip(), "root": os.path.normpath(self.root.strip()) if self.root.strip() else "",
                "compile_commands": json.dumps(cc), "build_root": opt(self.build_root),
                "swarm_url": opt(self.swarm_url), "settings": self.settings}


class DetectIn(BaseModel):
    root: str
```

Inside `create_app`, after the health/index/sinks handlers, add:

```python
    # ---- workspaces (spec 2026-10-31 §8) ----------------------------------------------
    def ws_row(ws: Workspace, logins: dict[str, str]) -> dict:
        """A workspace as the Workspaces page lists it; its owner also gets its fields, to edit."""
        mine = logins.get(ws.server) == ws.owner
        out = {**ws_ref(ws), "client": ws.cfg.workspace.client, "vcs": ws.cfg.workspace.vcs, "ready": ws.ready,
               "reason": ws.reason, "seed": ws.seed, "is_owner": mine}
        row = store.get_workspace(ws.id) if mine else None
        if row is not None:
            cc = json.loads(row["compile_commands"])
            out["fields"] = {**{k: row[k] for k in ("name", "vcs", "p4port", "client", "p4user", "root", "build_root",
                                                     "swarm_url", "settings")},
                             "compile_commands": "\n".join(cc) if isinstance(cc, list) else cc}
        return out

    def adder(logins: dict[str, str] = Depends(logins_of)) -> dict[str, str]:
        """Adding a workspace takes owner rights on at least one (§7; everyone signed in, with project 3)."""
        if not any(logins.get(w.server) == w.owner for w in reg.all()):
            raise HTTPException(403, "only the owner of a workspace adds workspaces")
        return logins

    def checked(ws: Workspace, logins: dict[str, str]) -> dict:
        return {**ws_row(ws, logins), "checks": [c.model_dump() for c in ws.checks]}

    def saved(change: Callable[[], Workspace], logins: dict[str, str]) -> dict:
        try:
            return checked(change(), logins)
        except Invalid as e:
            raise HTTPException(422, str(e)) from e
        except Conflict as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/api/workspaces")
    def list_workspaces(logins: dict[str, str] = Depends(logins_of)):
        """The workspaces on the session's servers."""
        return [ws_row(w, logins) for w in reg.all() if w.server in logins]

    @app.post("/api/workspaces")
    def add_workspace(body: WorkspaceIn, logins: dict[str, str] = Depends(adder)):
        """Saved even when its checks fail; the answer carries them (§11)."""
        if len(body.settings) > 100_000:
            raise HTTPException(422, "settings: at most 100000 characters")
        by = next(logins[w.server] for w in reg.all() if logins.get(w.server) == w.owner)
        return saved(lambda: reg.add(body.fields(), by), logins)

    @app.post("/api/workspaces/detect")
    def detect(body: DetectIn, _: dict[str, str] = Depends(adder)):
        """What `codetortoise init` finds at a root, to fill the add form: P4CONFIG's server, client and user, the
        client's Root, the compile databases."""
        if not os.path.isabs(body.root):
            raise HTTPException(422, "root: a full path on this host")
        p4_bin = reg.base.workspace.p4_bin if reg.base.workspace is not None else "p4"

        def client_root(port: str, client: str) -> str | None:
            recs = P4Runner(port, client, p4_bin, timeout=30, cwd=body.root).run("client", "-o", client)
            return recs[0].get("Root") if recs else None
        s = scan(Path(body.root), client_root=client_root)
        notes = ([] if Path(body.root).is_dir() else [f"{body.root} is not a folder on this host"]) + s.notes
        return {"root": str(s.root), "p4port": s.values["p4port"], "client": s.values["client"],
                "p4user": s.values["owner"], "compile_commands": [str(p) for p in s.compile_dbs],
                "client_root": s.client_root, "notes": notes}

    @app.put("/api/workspaces/{wid}")
    def edit_workspace(body: WorkspaceIn, o: Owned = Depends(owned)):
        """New fields, a new bundle swapped in; refused for the seed and while its queue has work (§6)."""
        if len(body.settings) > 100_000:
            raise HTTPException(422, "settings: at most 100000 characters")
        return saved(lambda: reg.edit(o.ws.id, body.fields()), o.logins)

    @app.delete("/api/workspaces/{wid}")
    def remove_workspace(o: Owned = Depends(owned)):
        try:
            reg.remove(o.ws.id)
        except Conflict as e:
            raise HTTPException(409, str(e)) from e
        return {"ok": True}
```

(`P4Runner` is already imported by Task 5.)

- [ ] **Step 4: Run the API tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_workspace_api.py -q`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd backend
git add codetortoise/web/app.py tests/test_workspace_api.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(web): the workspaces API — list, add with checks, detect from a root, edit, remove

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 7: Command line — `serve` on the registry, `--workspace` for the tools

**Files:**
- Modify: `backend/codetortoise/cli.py`
- Modify: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: Task 4's `Registry.open`, `Registry.load`, `Registry.tool_workspace`, `Workspace.svc/owner/id`; Task 5's `create_app(reg, authenticate)`, `make_authenticator(reg)`; Task 2's `create_review(..., workspace_id=)`.
- Produces: `codetortoise index|review|stories-check|check-parse --workspace NAME` (spec §10); `serve` exits 2 with the no-workspace message.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_cli.py`:

```python
def test_tools_work_on_the_workspace_named_else_the_seed(tmp_path, capsys):
    from codetortoise.store import Store
    assert main(["fixture-demo", "--dir", str(tmp_path), "--port", "9999"]) == 0
    cfg = str(tmp_path / "tortoise.yaml")
    assert main(["index", "--config", cfg]) == 0
    assert (tmp_path / "data" / "workspaces" / "1" / "symbols.db").exists()        # the seed's own folder
    assert main(["fixture-demo", "--dir", str(tmp_path / "b"), "--port", "9999"]) == 0
    store = Store(tmp_path / "data" / "tortoise.db")
    store.add_workspace({"name": "b", "vcs": "git", "p4port": None, "client": None, "p4user": "demo",
                         "root": str(tmp_path / "b" / "ws"), "compile_commands": json.dumps("auto"), "build_root": None,
                         "swarm_url": None, "settings": ""}, "ui", "demo")
    capsys.readouterr()
    assert main(["index", "--config", cfg, "--workspace", "b"]) == 0
    assert (tmp_path / "data" / "workspaces" / "2" / "symbols.db").exists()
    assert main(["index", "--config", cfg, "--workspace", "nope"]) == 2
    assert "no workspace named nope (there are: b, ws)" in capsys.readouterr().err
    assert main(["review", "--config", cfg, "--workspace", "b", "101"]) == 0
    assert store.get_review(1)["workspace_id"] == 2


def test_serve_without_a_workspace_names_both_ways_in(tmp_path, capsys):
    (tmp_path / "tortoise.yaml").write_text("auth: {mode: dev}\n")
    assert main(["serve", "--config", str(tmp_path / "tortoise.yaml")]) == 2
    err = capsys.readouterr().err
    assert "`workspace:` section" in err and "data folder" in err
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL — `error: unrecognized arguments: --workspace b` (argparse exits 2 with SystemExit), and `serve` fails in `_services` with `AttributeError: 'NoneType' object has no attribute 'compile_commands'`.

- [ ] **Step 3: Implement**

In `backend/codetortoise/cli.py`, replace `_services` and `cmd_serve`:

```python
def _workspace(args):
    """The workspace a tool works on (spec 2026-10-31 §10): --workspace, else the seed, else the only one."""
    from codetortoise.workspaces import Registry
    return Registry.open(load_config(Path(args.config))).tool_workspace(args.workspace)


def cmd_serve(args) -> int:
    import uvicorn

    from codetortoise.web.app import create_app, make_authenticator
    from codetortoise.workspaces import Registry
    reg = Registry.open(load_config(Path(args.config)))
    reg.load()                                       # bundles build in the background; a broken one never stops us
    app = create_app(reg, make_authenticator(reg))
    if reg.base.auth.mode == "dev":
        logging.warning("auth.mode=dev: any username logs in without a password. Do not expose this server.")
    srv = reg.base.server
    warning = plain_http_warning(srv)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)
        logging.warning(warning)
    uvicorn.run(app, host=srv.host, port=srv.port,
                ssl_certfile=str(srv.tls_cert) if srv.tls_cert else None,
                ssl_keyfile=str(srv.tls_key) if srv.tls_key else None)
    return 0


def cmd_index(args) -> int:
    svc = _workspace(args).svc
    n = svc.build_index(full=args.full)
    print(f"indexed {n} files (generation {svc.index.generation()})")
    return 0


def cmd_review(args) -> int:
    from codetortoise.pipeline import run_review
    ws = _workspace(args)
    svc = ws.svc
    rid = svc.store.create_review(args.title or f"CLs {args.cls}", ws.owner, args.cls, workspace_id=ws.id)
    run_review(rid, svc)
```

(the rest of `cmd_review` unchanged). In `cmd_stories_check` and `cmd_check_parse`, `svc = _services(args.config)` becomes `svc = _workspace(args).svc`.

In `main`, add to the `index`, `review`, `stories-check` and `check-parse` parsers (after their `--config`):

```python
    s.add_argument("--workspace", help="the workspace's name (default: the one in tortoise.yaml, else the only one)")
```

- [ ] **Step 4: Run the CLI tests, then the whole suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cli.py -q`
Expected: all pass (`test_bad_config_exit_code` still exits 2: a file with no workspace and an empty data folder is "no workspace to serve").

Run: `cd backend && .venv/bin/python -m pytest -q 2>&1 | tail -3` and `.venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd backend
git add codetortoise/cli.py tests/test_cli.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(cli): serve hosts every workspace; index, review, stories-check and check-parse take --workspace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 8: The UI on per-server sign-in — the sign-in form, the account menu, who the viewer is inside a review, a Health page per workspace

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/api.test.ts`
- Create: `frontend/src/viewer.ts`, `frontend/src/viewer.test.ts`
- Create: `frontend/src/lib/signin.ts`, `frontend/src/lib/signin.test.ts`
- Modify: `frontend/src/lib/reviewFilter.ts`, `frontend/src/lib/reviewFilter.test.ts`
- Create: `frontend/src/components/SignInForm.tsx`
- Modify: `frontend/src/pages/Login.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/Health.tsx`, `frontend/src/pages/Reviews.tsx`
- Modify: `frontend/src/workspace/useReview.ts`, `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/components/SinkMark.tsx`, `frontend/src/components/Comments.tsx`, `frontend/src/workspace/FindingBody.tsx`, `frontend/src/workspace/ClPage.tsx`, `frontend/src/workspace/ReviewMenu.tsx`
- Modify: `frontend/src/styles.css`, `frontend/src/workspace/workspace.css`
- Modify: `frontend/e2e/landing.spec.ts`, `frontend/e2e/workspace-tier1.spec.ts`, `frontend/e2e/workspace-sinks.spec.ts` (the moved endpoints)

**Interfaces:**
- Consumes (HTTP, Tasks 5–6): `GET /api/servers` → `[{server, user|null}]`; `POST /api/login {server?, user, password}` → `{server, user}`; `GET /api/me` → `{logins: [{server, user}], owner_of: [ids]}`; `GET /api/workspaces` → rows `{id, name, server, client, vcs, ready, reason, seed, is_owner, fields?}`; `GET /api/reviews` rows with `workspace: {id, name, server}`; `POST /api/reviews {workspace_id?, cls, title?}`; `GET /api/reviews/{id}` with `workspace` and `viewer: {user, is_owner}`; the 401 `{"detail": "sign in required", "server": "<server>"}`; `GET /api/workspaces/{id}/health`, `POST /api/workspaces/{id}/index/rebuild`, `GET|PUT|DELETE /api/workspaces/{id}/sinks[/label]`.
- Produces:
  - `api.ts`: types `Login {server, user}`, `Me {logins: Login[]; owner_of: number[]}`, `ServerRow {server; user: string | null}`, `WorkspaceRef {id; name; server}`, `WorkspaceFields`, `WorkspaceRow`; `ReviewRow.workspace?: WorkspaceRef`; `ReviewDetail.workspace: WorkspaceRef`, `ReviewDetail.viewer: {user; is_owner}`; `ApiError(status, message, server: string | null = null)`; `api.servers()`, `api.login(server: string | null, user, password)`, `api.workspaces()`, `api.health(wid)`, `api.rebuildIndex(wid)`, `api.createReview(cls, title?, workspace_id?)`, `api.sinks(wid)`, `api.markSink(wid, label)`, `api.unmarkSink(wid, label)`.
  - `viewer.ts`: `interface Viewer {user; is_owner; workspace: WorkspaceRef}`, `ViewerContext`, `useViewer(): Viewer | null`, `viewerOf(d: ReviewDetail | null): Viewer | null`.
  - `lib/signin.ts`: `pickerShown(servers, fixed?)`, `startServer(servers, asked?)`, `accountLabel(logins)`, `userOn(logins, server)`.
  - `lib/reviewFilter.ts`: `type Who = Record<string, string>` (server → user); `filterReviews(rows, query, chip, who)`, `chipCounts(rows, who)`.
  - `components/SignInForm.tsx`: `SignInForm({fixed?, asked?, onDone: () => Promise<unknown>})`.
  - `App.tsx`: `useMe()`, `useRefreshMe(): () => Promise<unknown>`; routes `/workspaces/:id` (a workspace's Health) and `/health` (redirect to the owner's workspace's Health).
  - `useReview(id)` result gains `signIn: string | null` (the server to sign in to before the review opens).
  - `pages/Health.tsx`: `Health({wid}: {wid: number})`.
  - Copy: the sign-in form's server picker is labelled `Perforce server`; the in-place prompt reads `Sign in to <server> to open this review`; the account menu's lines read `<server> as <user>` and `Sign in to another server`; the Health page has a `Recheck` button.

- [ ] **Step 1: Write the failing unit tests**

Create `frontend/src/viewer.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ReviewDetail } from "./api";
import { viewerOf } from "./viewer";

const detail = (viewer: ReviewDetail["viewer"]) =>
  ({ review: {}, cls: [], stages: [], workspace: { id: 2, name: "dsp", server: "second:1666" }, viewer }) as unknown as ReviewDetail;

describe("who the session is inside a review (spec 2026-10-31 §8)", () => {
  it("is the review's own viewer: the sign-in on its server, and whether that sign-in owns its workspace", () => {
    expect(viewerOf(detail({ user: "mallory", is_owner: false }))).toEqual(
      { user: "mallory", is_owner: false, workspace: { id: 2, name: "dsp", server: "second:1666" } });
    expect(viewerOf(detail({ user: "owner", is_owner: true }))?.is_owner).toBe(true);
  });

  it("is nobody until the review has loaded", () => {
    expect(viewerOf(null)).toBeNull();
  });
});
```

Create `frontend/src/lib/signin.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { accountLabel, pickerShown, startServer, userOn } from "./signin";

const ONE = [{ server: "local", user: null }];
const TWO = [{ server: "local", user: "amy" }, { server: "second:1666", user: null }];

describe("the sign-in picker (spec 2026-10-31 §9)", () => {
  it("shows only when there is a choice: several servers, and none asked for by a review", () => {
    expect(pickerShown(ONE)).toBe(false);
    expect(pickerShown(TWO)).toBe(true);
    expect(pickerShown(TWO, "second:1666")).toBe(false);
  });

  it("starts on the server asked for, else the first one not signed in to, else the first", () => {
    expect(startServer(TWO, "local")).toBe("local");
    expect(startServer(TWO)).toBe("second:1666");
    expect(startServer(TWO, "nowhere:1")).toBe("second:1666");
    expect(startServer([{ server: "local", user: "amy" }])).toBe("local");
    expect(startServer([])).toBeNull();
  });
});

describe("the account menu", () => {
  const logins = [{ server: "local", user: "amy" }, { server: "second:1666", user: "bob" }];

  it("names the first sign-in and counts the others", () => {
    expect(accountLabel(logins)).toBe("amy +1");
    expect(accountLabel(logins.slice(0, 1))).toBe("amy");
    expect(accountLabel([])).toBe("");
  });

  it("finds the session's user on a server", () => {
    expect(userOn(logins, "second:1666")).toBe("bob");
    expect(userOn(logins, "third:1")).toBeNull();
    expect(userOn(logins, undefined)).toBeNull();
  });
});
```

Replace `frontend/src/lib/reviewFilter.test.ts` with:

```ts
import { describe, expect, it } from "vitest";
import type { ReviewRow } from "../api";
import { chipCounts, filterReviews, highlight } from "./reviewFilter";

const LOCAL = { id: 1, name: "fw", server: "local" }, SECOND = { id: 2, name: "dsp", server: "second:1666" };
const row = (id: number, title: string, cls: number[], status: string, risk: ReviewRow["risk"], by = "amy", workspace = LOCAL) =>
  ({ id, title, cls, status, risk, created_by: by, created_at: "2026-10-01T10:00:00+00:00", workspace }) as ReviewRow;
const rows = [
  row(1, "Detached HEAD caching", [28, 29], "done", "high"),
  row(2, "planted: output_eol -1", [30], "degraded", "high", "bob"),
  row(3, "upstream 24", [24], "running", "low"),
  row(4, "queued one", [7], "queued", null, "bob"),
];
const ids = (r: ReviewRow[]) => r.map((x) => x.id);
const AMY = { local: "amy" };                               // the session: amy, signed in to local only

describe("review search", () => {
  it("matches title, CL number, author and status, ignoring case", () => {
    expect(ids(filterReviews(rows, "detach", "all", AMY))).toEqual([1]);
    expect(ids(filterReviews(rows, "30", "all", AMY))).toEqual([2]);
    expect(ids(filterReviews(rows, "CL 24", "all", AMY))).toEqual([3]);
    expect(ids(filterReviews(rows, "BOB", "all", AMY))).toEqual([2, 4]);
    expect(ids(filterReviews(rows, "degraded", "all", AMY))).toEqual([2]);
    expect(ids(filterReviews(rows, "  ", "all", AMY))).toEqual([1, 2, 3, 4]);
    expect(ids(filterReviews(rows, "head caching", "all", AMY))).toEqual([1]);   // every word must match
  });

  it("filters by chip and counts each chip", () => {
    expect(ids(filterReviews(rows, "", "high", AMY))).toEqual([1, 2]);
    expect(ids(filterReviews(rows, "", "running", AMY))).toEqual([3, 4]);       // queued counts as running
    expect(ids(filterReviews(rows, "", "mine", AMY))).toEqual([1, 3]);
    expect(ids(filterReviews(rows, "planted", "mine", AMY))).toEqual([]);
    expect(chipCounts(rows, AMY)).toEqual({ all: 4, high: 2, running: 2, mine: 2 });
  });

  it("counts as Mine a review made by the session's sign-in on that review's own server", () => {
    const two = [...rows, row(5, "same name elsewhere", [9], "done", null, "amy", SECOND), row(6, "theirs", [10], "done", null, "bob", SECOND)];
    expect(ids(filterReviews(two, "", "mine", AMY))).toEqual([1, 3]);              // amy on local is not the amy of second:1666
    expect(ids(filterReviews(two, "", "mine", { local: "amy", "second:1666": "bob" }))).toEqual([1, 3, 6]);
    expect(chipCounts(two, {}).mine).toBe(0);
  });

  it("splits a title into highlighted and plain parts", () => {
    expect(highlight("Detached HEAD caching", "head detach")).toEqual([
      { text: "Detach", hit: true }, { text: "ed ", hit: false }, { text: "HEAD", hit: true }, { text: " caching", hit: false }]);
    expect(highlight("upstream 24", "")).toEqual([{ text: "upstream 24", hit: false }]);
    expect(highlight("a.b(c)", "(c")).toEqual([{ text: "a.b", hit: false }, { text: "(c", hit: true }, { text: ")", hit: false }]);
  });
});
```

In `frontend/src/api.test.ts`, change the first two lines to

```ts
import { describe, expect, it, vi } from "vitest";
import { api, ApiError, errorText } from "./api";
```

and append:

```ts
describe("a refusal that names a Perforce server", () => {
  it("carries the server a review asks the session to sign in to (spec 2026-10-31 §7), and none otherwise", async () => {
    const refused = (status: number, body: object) => vi.stubGlobal("fetch", async () => new Response(JSON.stringify(body), { status }));
    const failure = () => api.review(7).then(() => null, (e: unknown) => e as ApiError);
    try {
      refused(401, { detail: "sign in required", server: "second:1666" });
      const e = await failure();
      expect(e).toBeInstanceOf(ApiError);
      expect([e?.status, e?.message, e?.server]).toEqual([401, "sign in required", "second:1666"]);
      refused(403, { detail: "owner only" });
      expect((await failure())?.server).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run 2>&1 | tail -25`
Expected: FAIL — `src/viewer.test.ts` and `src/lib/signin.test.ts` cannot import their modules (`Failed to resolve import "./viewer"`, `"./signin"`); in `reviewFilter.test.ts` every `mine` expectation gets `[]` (the old code compares `created_by` with the `{local: "amy"}` object); in `api.test.ts` the error's `server` is `undefined`.

- [ ] **Step 3: Implement the API types, the viewer, the sign-in helpers and "Mine" per server**

In `frontend/src/api.ts`, replace the line `export interface Me { user: string; is_owner: boolean; swarm_ready: boolean }` with:

```ts
/** A sign-in: the session's user on one Perforce server (spec 2026-10-31 §7). */
export interface Login { server: string; user: string }
/** The session (spec 2026-10-31 §8): one sign-in per Perforce server, and the workspaces it owns. Inside a review, who the
 * session is comes from the review's `viewer` instead (viewer.ts). */
export interface Me { logins: Login[]; owner_of: number[] }
/** A Perforce server some workspace is on, and the session's user there (null: not signed in to it). */
export interface ServerRow { server: string; user: string | null }
/** The workspace a review belongs to. */
export interface WorkspaceRef { id: number; name: string; server: string }
/** A workspace's settings as its owner edits them (spec 2026-10-31 §9); `compile_commands` is "auto", a path, or one per line. */
export interface WorkspaceFields {
  name: string; vcs: "p4" | "git"; p4port: string | null; client: string | null; p4user: string; root: string;
  compile_commands: string; build_root: string | null; swarm_url: string | null; settings: string;
}
/** A workspace as the Workspaces page lists it (spec 2026-10-31 §8); `fields` only for its owner. */
export interface WorkspaceRow extends WorkspaceRef {
  client: string | null; vcs: "p4" | "git"; ready: boolean; reason: string | null; seed: boolean; is_owner: boolean;
  fields?: WorkspaceFields;
}
```

In `ReviewRow`, after the `headline?: Headline | null;` line add:

```ts
  /** Its workspace (spec 2026-10-31 §8); not on the answer to a review just created. */
  workspace?: WorkspaceRef;
```

Replace the `ReviewDetail` line with:

```ts
/** A review, its CLs and stages, its workspace, and who the session is inside it: its sign-in on the review's server
 * (spec 2026-10-31 §8). */
export interface ReviewDetail { review: ReviewRow; cls: ClRow[]; stages: Stage[]; workspace: WorkspaceRef; viewer: { user: string; is_owner: boolean } }
```

Replace `ApiError` and the error branch of `call`:

```ts
export class ApiError extends Error {
  /** `server`: the Perforce server to sign in to, on a 401 for a review there (spec 2026-10-31 §7). */
  constructor(public status: number, message: string, public server: string | null = null) { super(message); }
}
```

```ts
  if (!res.ok) {
    let msg = res.statusText, server: string | null = null;
    try {
      const body = await res.json();
      msg = body.detail ?? msg;
      if (typeof body.server === "string") server = body.server;
    } catch { /* not json */ }
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg), server);
  }
```

In `export const api = {…}`, replace the `login`, `health`, `rebuildIndex` and `createReview` lines with:

```ts
  /** The Perforce servers of all workspaces, with the session's user on each (the sign-in form's picker). */
  servers: () => call<ServerRow[]>("GET", "/api/servers"),
  /** Sign in to `server` (null: the only one there is), adding to the session's sign-ins. */
  login: (server: string | null, user: string, password: string) =>
    call<Login>("POST", "/api/login", { server: server ?? undefined, user, password }),
```

```ts
  /** The workspaces on the session's servers (spec 2026-10-31 §8). */
  workspaces: () => call<WorkspaceRow[]>("GET", "/api/workspaces"),
  health: (wid: number) => call<Health>("GET", `/api/workspaces/${wid}/health`),
  rebuildIndex: (wid: number) => call("POST", `/api/workspaces/${wid}/index/rebuild`),
```

```ts
  /** A review in workspace `workspace_id` (left out: the only workspace there is). */
  createReview: (cls: number[], title?: string, workspace_id?: number) =>
    call<ReviewRow>("POST", "/api/reviews", { workspace_id, cls, title }),
```

and replace the three shared-sink lines (with their comment) at the end with:

```ts
  /** A workspace's shared sinks (spec 2026-10-09 §6; per workspace since spec 2026-10-31 §5): the rules, and its owner's marks for
   * every review of it from the next run. */
  sinks: (wid: number) => call<SinkRules>("GET", `/api/workspaces/${wid}/sinks`),
  markSink: (wid: number, label: string) => call<SinkRules>("PUT", `/api/workspaces/${wid}/sinks/${encodeURIComponent(label)}`),
  unmarkSink: (wid: number, label: string) => call<SinkRules>("DELETE", `/api/workspaces/${wid}/sinks/${encodeURIComponent(label)}`),
```

Create `frontend/src/viewer.ts`:

```ts
/** Who the session is inside a review (spec 2026-10-31 §8): its sign-in on the review's server, and whether that sign-in owns
 * the review's workspace. Inside a review the UI asks this, never `/api/me`, whose sign-ins span servers: the same name on
 * another server is someone else. */
import { createContext, useContext } from "react";
import type { ReviewDetail, WorkspaceRef } from "./api";

export interface Viewer { user: string; is_owner: boolean; workspace: WorkspaceRef }

export const ViewerContext = createContext<Viewer | null>(null);
export const useViewer = () => useContext(ViewerContext);

/** The viewer a review's detail names; null until it has loaded. */
export function viewerOf(d: ReviewDetail | null): Viewer | null {
  return d ? { ...d.viewer, workspace: d.workspace } : null;
}
```

Create `frontend/src/lib/signin.ts`:

```ts
/** Sign-in per Perforce server (spec 2026-10-31 §7, §9) (pure): what the sign-in form offers and what the account menu says. */
import type { Login, ServerRow } from "../api";

/** The picker shows only when there is a choice: several servers, and no server fixed by the review asking. */
export function pickerShown(servers: ServerRow[], fixed?: string | null): boolean {
  return !fixed && servers.length > 1;
}

/** The server the form starts on: the one asked for, else the first the session isn't signed in to, else the first. */
export function startServer(servers: ServerRow[], asked?: string | null): string | null {
  if (asked && servers.some((s) => s.server === asked)) return asked;
  return (servers.find((s) => !s.user) ?? servers[0])?.server ?? null;
}

/** The account menu's button: the first sign-in's user, and how many more sign-ins there are ("amy +1"). */
export function accountLabel(logins: Login[]): string {
  if (!logins.length) return "";
  return logins.length > 1 ? `${logins[0].user} +${logins.length - 1}` : logins[0].user;
}

/** The session's user on `server`, or null. */
export function userOn(logins: Login[], server: string | undefined): string | null {
  return logins.find((l) => l.server === server)?.user ?? null;
}
```

In `frontend/src/lib/reviewFilter.ts`, replace everything from `export type Chip` through the end of `chipCounts` with:

```ts
export type Chip = "all" | "high" | "running" | "mine";
/** The session's user on each Perforce server it is signed in to (spec 2026-10-31 §7). */
export type Who = Record<string, string>;
const RUNNING = new Set(["queued", "running"]);

const words = (q: string) => q.toLowerCase().split(/\s+/).filter(Boolean);
const haystack = (r: ReviewRow) =>
  [r.title, r.created_by, r.status, ...r.cls.map((c) => `${c} cl ${c} cl${c}`)].join(" ").toLowerCase();
/** Made by the session's sign-in on the review's own server: the same name on another server is someone else. */
const mine = (r: ReviewRow, who: Who) => !!r.workspace && who[r.workspace.server] === r.created_by;

function chipOk(r: ReviewRow, chip: Chip, who: Who) {
  return chip === "all" || (chip === "high" && r.risk === "high") || (chip === "running" && RUNNING.has(r.status))
    || (chip === "mine" && mine(r, who));
}

/** Rows matching every word of the query (title, CL number, author, status) and the chip. */
export function filterReviews(rows: ReviewRow[], query: string, chip: Chip, who: Who): ReviewRow[] {
  const ws = words(query.replace(/\bcl\s+(\d+)/gi, "cl$1"));
  return rows.filter((r) => chipOk(r, chip, who) && ws.every((w) => haystack(r).includes(w)));
}

export function chipCounts(rows: ReviewRow[], who: Who): Record<Chip, number> {
  const n = (c: Chip) => rows.filter((r) => chipOk(r, c, who)).length;
  return { all: n("all"), high: n("high"), running: n("running"), mine: n("mine") };
}
```

- [ ] **Step 4: Run the unit tests**

Run: `cd frontend && npx vitest run 2>&1 | tail -5`
Expected: all test files pass.

- [ ] **Step 5: The sign-in form, the login page and the account menu**

Create `frontend/src/components/SignInForm.tsx`:

```tsx
import { type FormEvent, useEffect, useState } from "react";
import { api, errorText, type ServerRow } from "../api";
import { pickerShown, startServer } from "../lib/signin";
import Logo from "./Logo";

/** The sign-in form (spec 2026-10-31 §9): the Perforce server (a picker, hidden with one server), the user and the password.
 * `fixed`: the server a review asks for (its prompt says so, and there is no picker); `asked`: the server to start on.
 * `onDone` runs once the server accepts the sign-in; the button waits for it. */
export default function SignInForm({ fixed = null, asked = null, onDone }:
  { fixed?: string | null; asked?: string | null; onDone: () => Promise<unknown> }) {
  const [servers, setServers] = useState<ServerRow[] | null>(null);
  const [server, setServer] = useState<string | null>(fixed);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (fixed) return;
    api.servers().then((s) => { setServers(s); setServer((now) => now ?? startServer(s, asked)); })
      .catch(() => setServers([]));                 // the server then takes the only one there is, or says to choose
  }, [fixed, asked]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(server, user.trim(), password);
      await onDone();
    } catch (err) {
      setError(errorText(err, "You could not be signed in."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="login-card stack">
      <Logo size={64} />
      <h1>CodeTortoise</h1>
      <p className="muted">{fixed ? `Sign in to ${fixed} to open this review` : "Sign in with your Perforce account"}</p>
      {servers && pickerShown(servers, fixed) && (
        <label>Perforce server
          <select value={server ?? ""} onChange={(e) => setServer(e.target.value)}>
            {servers.map((s) => <option key={s.server} value={s.server}>{s.server}{s.user ? ` (signed in as ${s.user})` : ""}</option>)}
          </select>
        </label>
      )}
      <label>P4 user<input autoFocus value={user} onChange={(e) => setUser(e.target.value)} required /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      {error && <div className="error" role="alert">{error}</div>}
      {/* until the servers are known, the one to sign in to isn't */}
      <button className="go" disabled={busy || !user.trim() || (!fixed && servers === null)}>{busy ? "Checking…" : "Sign in"}</button>
    </form>
  );
}
```

Replace `frontend/src/pages/Login.tsx` with:

```tsx
import { useNavigate, useSearchParams } from "react-router-dom";
import SignInForm from "../components/SignInForm";

/** The sign-in page (spec 2026-10-31 §9): `?server=` starts the form on that server, `?next=` is where it goes after. */
export default function Login({ onLogin }: { onLogin: () => Promise<unknown> }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  return (
    <main className="login-wrap">
      <SignInForm asked={params.get("server")} onDone={async () => { await onLogin(); navigate(params.get("next") || "/"); }} />
    </main>
  );
}
```

Replace `frontend/src/App.tsx` with:

```tsx
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, type Me } from "./api";
import InsecureBanner from "./components/InsecureBanner";
import Logo from "./components/Logo";
import ThemeSwitch from "./components/ThemeSwitch";
import { accountLabel } from "./lib/signin";
import Health from "./pages/Health";
import Login from "./pages/Login";
import Reviews from "./pages/Reviews";
import Workspace from "./workspace/Workspace";

/** One workspace per review: moving to another review starts it afresh, so nothing of the last one (an error, its
 * memory, a late answer) carries over. */
function ReviewRoute() {
  const { id } = useParams();
  return <Workspace key={id} />;
}

/** `/w/` was the workspace's address while it was built; it is `/r/` now. */
function ToReview() {
  const { id, "*": rest } = useParams(), { search, hash } = useLocation();
  return <Navigate to={`/r/${id}${rest ? `/${rest}` : ""}${search}${hash}`} replace />;
}

/** A workspace's Health page, afresh for each workspace (spec 2026-10-31 §9). */
function HealthRoute() {
  const { id } = useParams();
  return <Health key={id} wid={Number(id)} />;
}

/** `/health` was the one workspace's Health page; each workspace has its own now (spec 2026-10-31 §8). */
function ToHealth() {
  const first = useMe()?.owner_of[0];
  return <Navigate to={first === undefined ? "/" : `/workspaces/${first}`} replace />;
}

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);
const RefreshMeContext = createContext<() => Promise<unknown>>(() => Promise.resolve());
/** Load the session again, so the top bar follows a sign-in made in place (a review's prompt). */
export const useRefreshMe = () => useContext(RefreshMeContext);

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const location = useLocation();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const refreshMe = useCallback(() => api.me().then(setMe), []);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
    setMenu(false);
  }, [location.pathname]);

  if (me === undefined) return <div className="page muted">Loading…</div>;
  if (me === null && location.pathname !== "/login")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  const here = location.pathname === "/login" ? "/" : location.pathname + location.search;

  return (
    <MeContext.Provider value={me}>
      <RefreshMeContext.Provider value={refreshMe}>
        <InsecureBanner />
        <header className={`topbar${menu ? " open" : ""}`}>
          <Link to="/" className="brand"><Logo size={28} />CodeTortoise</Link>
          {me && (
            <button className="menu-btn" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button>
          )}
          {me && (
            <nav>
              <Link to="/">Reviews</Link>
              {me.owner_of.length > 0 && <Link to="/health">Health</Link>}
              {/* the account menu (spec 2026-10-31 §9): a line per sign-in, and signing in to another server; shut again on
                  each move */}
              <details className="account" key={location.pathname}>
                <summary>{accountLabel(me.logins)}</summary>
                <ul>
                  {me.logins.map((l) => <li key={l.server}>{l.server} as {l.user}</li>)}
                  <li><Link to={`/login?next=${encodeURIComponent(here)}`}>Sign in to another server</Link></li>
                </ul>
              </details>
              <button className="link" onClick={() => api.logout().then(() => { setMe(null); navigate("/login"); })}>
                Log out
              </button>
            </nav>
          )}
          <ThemeSwitch />
        </header>
        <Routes>
          <Route path="/login" element={<Login onLogin={refreshMe} />} />
          <Route path="/" element={<Reviews />} />
          <Route path="/new" element={<Navigate to="/" replace />} />
          <Route path="/health" element={<ToHealth />} />
          <Route path="/workspaces/:id" element={<HealthRoute />} />
          <Route path="/r/:id/*" element={<ReviewRoute />} />
          <Route path="/w/:id/*" element={<ToReview />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </RefreshMeContext.Provider>
    </MeContext.Provider>
  );
}
```

- [ ] **Step 6: A Health page per workspace, and the Reviews page on per-server sign-ins**

Replace `frontend/src/pages/Health.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { api, errorText, type Health as HealthT, type SinkRules, type WorkspaceRow } from "../api";
import { useMe } from "../App";
import SinkMark from "../components/SinkMark";
import { userOn } from "../lib/signin";
import { ViewerContext } from "../viewer";

/** A workspace's Health page (spec 2026-10-31 §9: today's Health page, for that workspace), for its owner: its checks, run
 * again by Recheck (§11), its symbol index, the flags libclang rejected, the AI limits and its shared sinks. */
export default function Health({ wid }: { wid: number }) {
  const me = useMe();
  const [h, setH] = useState<HealthT | null>(null);
  const [ws, setWs] = useState<WorkspaceRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [sinks, setSinks] = useState<SinkRules | null>(null);
  const [sinksError, setSinksError] = useState<string | null>(null);       // the card says so; what it showed before stays
  const loadSinks = () => api.sinks(wid).then((s) => { setSinks(s); setSinksError(null); })
    .catch((e) => setSinksError(errorText(e, "The shared sinks could not be loaded.")));
  const load = () => {
    loadSinks();
    api.workspaces().then((all) => setWs(all.find((w) => w.id === wid) ?? null)).catch(() => { /* the heading goes without its name */ });
    return api.health(wid).then(setH).catch((e) => setError(errorText(e, "The health checks could not be loaded.")));
  };
  const recheck = () => { setChecking(true); load().finally(() => setChecking(false)); };
  useEffect(() => { load(); }, []);

  if (error) return <main className="page error"><div role="alert">{error}</div></main>;
  if (!h) return <main className="page muted">Checking…</main>;
  // the marks below act on this workspace as its owner: only its owner gets this page
  const viewer = { user: userOn(me?.logins ?? [], ws?.server) ?? "", is_owner: true,
                   workspace: { id: wid, name: ws?.name ?? "", server: ws?.server ?? "" } };
  return (
    <ViewerContext.Provider value={viewer}>
      <main className="page">
        <div className="hc-head">
          <h1 className="hc-title">Health{ws ? ` · ${ws.name}` : ""} <span className={`hc-pill ${h.ready ? "ok" : "bad"}`}>● {h.ready ? "ready" : "not ready"}</span></h1>
          <button onClick={recheck} disabled={checking}>{checking ? "Checking…" : "Recheck"}</button>
        </div>
        {h.checks.flatMap((c) => /code from reviewed changes is sent to (\S+)/.exec(c.detail)?.[1] ?? []).map((host) => (
          <div key={host} className="banner warn" role="note">Code from reviewed changes is sent to <b>{host}</b>, the strong
            model's endpoint. Point <code>llm.strong.base_url</code> at a model on your network to keep it in house.</div>
        ))}
        <div className="hc-list">
          {h.checks.map((c) => {
            const kind = c.ok ? "ok" : c.hard ? "bad" : "warn";
            return (
              <div key={c.name} className={`hc-row ${kind}`}>
                <span className="icon">{c.ok ? "✓" : c.hard ? "✗" : "!"}</span>
                <div><b>{c.name}</b>{!c.hard && <span className="muted small"> · warning only</span>}<div className="detail">{c.detail}</div></div>
              </div>
            );
          })}
        </div>
        <div className="hc-cards">
          <section className="card">
            <h2>Symbol index</h2>
            <p>Generation {h.index_generation}{h.index_building ? " — rebuilding…" : ""}</p>
            <button onClick={() => api.rebuildIndex(wid).then(load)}>Rebuild index</button>
          </section>
          <section className="card">
            <h2>Flags stripped for libclang</h2>
            <p className="mono small">{h.strip_flags.length ? h.strip_flags.join(" ") : "none"}</p>
          </section>
          {h.ai?.limits && (
            <section className="card">
              <h2>AI calls</h2>
              <p className="small">Limits: {h.ai.limits.per_review} a review · {h.ai.limits.per_person_daily} a person a day ·{" "}
                {h.ai.limits.per_mention} rounds for one @tortoise answer (1 call; owners can change it per review)</p>
              <p className="small">Today: {h.ai.calls_today ?? 0} calls across reviews</p>
            </section>
          )}
          {(sinks || sinksError) && (
            <section className="card">
              <h2>Shared sinks</h2>
              {sinksError && <p className="error" role="alert">{sinksError}</p>}
              {sinks && (
                <>
                  <p>{sinks.threshold > 0 ? `A field more than ${sinks.threshold} unchanged functions touch` : "No threshold (sink_threshold: 0)"}</p>
                  <p className="mono small">In tortoise.yaml: {sinks.patterns.length ? sinks.patterns.join(" ") : "none"}</p>
                  <p>Marked: {sinks.marked.length ? sinks.marked.map((m) => <span key={m}><code>{m}</code> <SinkMark label={m} on onDone={loadSinks} /> </span>) : "none"}</p>
                </>
              )}
            </section>
          )}
          {Object.keys(h.p4_sources ?? {}).length > 0 && (
            <section className="card">
              <h2>Perforce settings from</h2>
              {Object.entries(h.p4_sources).map(([k, v]) => <p key={k} className="small"><b>{k}</b> · {v}</p>)}
            </section>
          )}
        </div>
        <p className="muted small">Code snippets of changed functions and their callers are sent to the configured LLM endpoint.</p>
      </main>
    </ViewerContext.Provider>
  );
}
```

In `frontend/src/pages/Reviews.tsx`:

Replace the two lines

```tsx
  const shown = useMemo(() => (rows ? filterReviews(rows, query, chip, me?.user ?? null) : []), [rows, query, chip, me]);
  const counts = useMemo(() => chipCounts(rows ?? [], me?.user ?? null), [rows, me]);
```

with

```tsx
  const who = useMemo(() => Object.fromEntries((me?.logins ?? []).map((l) => [l.server, l.user])), [me]);
  const shown = useMemo(() => (rows ? filterReviews(rows, query, chip, who) : []), [rows, query, chip, who]);
  const counts = useMemo(() => chipCounts(rows ?? [], who), [rows, who]);
  const owner = !!me?.owner_of.length;                     // owns a workspace: starts reviews (spec 2026-10-31 §7)
```

replace `{me?.is_owner ? <StartReview /> : (` with `{me && owner ? <StartReview wid={me.owner_of.length === 1 ? me.owner_of[0] : undefined} /> : (`, replace `<h1>Hi {me?.user}</h1>` with `<h1>Hi {[...new Set((me?.logins ?? []).map((l) => l.user))].join(", ")}</h1>`, and in the empty-list line replace `me?.is_owner` with `owner`.

Replace `function StartReview() {` with `function StartReview({ wid }: { wid?: number }) {` and its call `api.createReview(cls, title.trim() || undefined)` with `api.createReview(cls, title.trim() || undefined, wid)`. (Task 9 gives New review its workspace picker.)

- [ ] **Step 7: Inside a review — the in-place sign-in, the viewer, the workspace's name**

In `frontend/src/workspace/useReview.ts`, after the `const [error, setError] = …` line add

```ts
  const [signIn, setSignIn] = useState<string | null>(null);   // the server to sign in to before this review opens (spec 2026-10-31 §9)
```

replace the `fail` and `loadDetail` lines with

```ts
  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401 && e.server) setSignIn(e.server);   // a review on a server the session isn't signed in to
    else setError(errorText(e, "The review could not be loaded."));
  }, []);
  const loadDetail = useCallback(() => api.review(id).then((d) => { setSignIn(null); setDetail(d); }).catch(fail), [id, fail]);
```

and in the returned `useMemo`, add `signIn` after `error` in both the object (`… about, reload, error, signIn,`) and the dependency list (`… reload, error, signIn, ready, ai,`).

In `frontend/src/workspace/Workspace.tsx`:

- imports: after `import { api } from "../api";` add `import { useRefreshMe } from "../App";`; after `import HeadlinePill from "../components/HeadlinePill";` add `import SignInForm from "../components/SignInForm";`; after `import type { CheckKind } from "../reading/types";` add `import { ViewerContext, viewerOf } from "../viewer";`.
- after `const data = useReview(id);` add

```tsx
  const refreshMe = useRefreshMe();
  const viewer = useMemo(() => viewerOf(data.detail), [data.detail]);   // who the session is in this review (spec 2026-10-31 §8)
```

- replace `  if (data.error) return <main className="page error"><div role="alert">{data.error}</div></main>;` with

```tsx
  if (data.signIn)                                         // its server has no sign-in in this session: the form, in place (§9)
    return (
      <main className="login-wrap">
        <SignInForm fixed={data.signIn} onDone={() => Promise.all([refreshMe(), data.loadDetail()])} />
      </main>
    );
  if (data.error) return <main className="page error"><div role="alert">{data.error}</div></main>;
```

- replace the component's final `return (` block — from `<AiProvider value={data.ai}>` to `</AiProvider>` — with

```tsx
  return (
    <AiProvider value={data.ai}>
      <ViewerContext.Provider value={viewer}>
        <WsContext.Provider value={ws}>
          <main className={`ws ${screen} level-${level}${drawer ? " drawer" : ""}`}>
            <Head onMenu={() => setDrawer(!drawer)} drawer={drawer} />
            <div className={`ws-body${addr.open ? " with-detail" : ""}`}>
              {(screen !== "phone" || level === "rail") && (r === null      // the old rail only for a review run before the reading
                ? <Rail show={hash} onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />
                : <Outline onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />)}
              {drawer && <div className="ws-scrim" onClick={() => setDrawer(false)} aria-hidden />}
              {(screen !== "phone" || level === "item") && (
                <section className="ws-centre" aria-label="Centre">
                  {screen === "phone" ? <PhoneBar {...phoneBar(trail)} /> : <Crumbs items={trail} />}
                  <Centre />
                </section>
              )}
              {addr.open && d && data.ready && r !== undefined && (screen !== "phone" || level === "detail") && <Detail key={"cause" in addr.open ? `c:${addr.open.cause}` : JSON.stringify(addr.open)} />}
            </div>
          </main>
        </WsContext.Provider>
      </ViewerContext.Provider>
    </AiProvider>
  );
```

- in `Head`, change its first line to `const ws = useWs(), ai = useAi(), d = ws.data, r = d.detail!.review, where = d.detail!.workspace;` and after the `<h1>…</h1>` line add

```tsx
        <span className="ws-where" title={`Workspace ${where.name} on ${where.server}`}>{where.name}</span>
```

Then switch every component inside a review from `/api/me` to the review's viewer:

```bash
cd frontend
sed -i 's#^import { useMe } from "../App";$#import { useViewer } from "../viewer";#; s/\bme = useMe()/me = useViewer()/' \
  src/components/Comments.tsx src/workspace/FindingBody.tsx src/workspace/ClPage.tsx src/workspace/ReviewMenu.tsx
grep -rn "useMe" src
```

Expected: `useMe` only in `src/App.tsx`, `src/pages/Reviews.tsx` and `src/pages/Health.tsx` (and `SinkMark.tsx` until the next edit). `Viewer` has `user` and `is_owner`, so `me?.user` and `me?.is_owner` in those files stay as they are.

Replace the head of `frontend/src/components/SinkMark.tsx` — its imports through the `act` function — with:

```tsx
import { useContext, useState } from "react";
import { api, errorText } from "../api";
import { useViewer } from "../viewer";
import { WsContext } from "../workspace/context";

/** The owner's mark (spec 2026-10-09-shared-sinks §6.2): treat a field as a shared sink in every review of the workspace from
 * the next run, or stop. Inside a review it offers the re-run that applies it; `onDone` tells a list of marks to load again.
 * The workspace and the owner are the viewer's (spec 2026-10-31 §8): the review's, or the Health page's. */
export default function SinkMark({ label, on = false, onDone }: { label: string; on?: boolean; onDone?: () => void }) {
  const viewer = useViewer(), ws = useContext(WsContext);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!viewer?.is_owner) return null;
  const wid = viewer.workspace.id;
  const fail = (what: string) => (e: unknown) => setError(errorText(e, what));     // `what`: said when the server says nothing
  const act = () => {
    setError(null);                                // a new attempt clears the last failure, so a repeat is told again
    return (on ? api.unmarkSink(wid, label) : api.markSink(wid, label))
      .then(() => { setDone(true); onDone?.(); }, fail(`The field could not be ${on ? "unmarked" : "marked"} as a sink.`));
  };
```

(the rest of the file — `rerun`, `warn` and the two returns — is unchanged).

- [ ] **Step 8: Styles**

In `frontend/src/styles.css`, after the `.topbar nav a, .topbar nav button { white-space: nowrap; }` line add:

```css
/* the account menu (spec 2026-10-31 §9): a line per sign-in, and signing in to another server */
.topbar .account { position: relative; }
.topbar .account summary { cursor: pointer; color: var(--muted); white-space: nowrap; list-style: none; }
.topbar .account summary::-webkit-details-marker { display: none; }
.topbar .account summary::after { content: " ▾"; font-size: 11px; }
.topbar .account ul { position: absolute; right: 0; top: calc(100% + 8px); z-index: 30; min-width: 240px; margin: 0; padding: 6px 0;
  list-style: none; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 10px 28px rgba(0, 0, 0, .14); }
.topbar .account li { padding: 5px 14px; white-space: nowrap; }
```

inside the last `@media (max-width: 600px)` block (the one with `.menu-btn { display: inline-block; }`) add:

```css
  .topbar .account ul { position: static; min-width: 0; border: 0; box-shadow: none; padding: 4px 0 0; }
  .topbar .account li { padding: 3px 0; white-space: normal; overflow-wrap: anywhere; }
```

and after the `.hc-title { … }` line add:

```css
.hc-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; margin-bottom: 12px; }
.hc-head h1 { margin: 0; }
```

In `frontend/src/workspace/workspace.css`, after the `.ws-progress { … }` line add

```css
.ws-where { font-size: 12.5px; color: var(--muted); white-space: nowrap; }   /* the review's workspace (spec 2026-10-31 §9) */
```

and change `@media (max-width: 640px) { .ws-progress { display: none; } }` to `@media (max-width: 640px) { .ws-progress, .ws-where { display: none; } }`.

- [ ] **Step 9: The end-to-end specs follow the moved endpoints**

In `frontend/e2e/landing.spec.ts`, `page.route("**/api/health", …)` becomes `page.route("**/api/workspaces/*/health", …)` and `page.route("**/api/sinks", …)` becomes `page.route("**/api/workspaces/*/sinks", …)` (`/health` itself still works: it goes to the owner's workspace's Health page).

In `frontend/e2e/workspace-tier1.spec.ts`, `page.route("**/api/health*", …)` becomes `page.route("**/api/workspaces/*/health*", …)`.

In `frontend/e2e/workspace-sinks.spec.ts`, after the `const READER = …` line add

```ts
/** The marks of this server's one workspace, the seed (spec 2026-10-31 §8). */
const MARKS = "/api/workspaces/1/sinks";
```

and run

```bash
cd frontend
sed -i -e 's#`/api/sinks/#`${MARKS}/#g' -e 's#"\*\*/api/sinks/\*"#"**/api/workspaces/*/sinks/*"#g' \
  -e 's#"\*\*/api/sinks"#"**/api/workspaces/*/sinks"#g' e2e/workspace-sinks.spec.ts
grep -rn "api/sinks\|api/health\|api/index" e2e/*.ts
```

Expected: the grep prints nothing.

- [ ] **Step 10: Type-check, unit tests, build, then the whole end-to-end suite**

Run: `cd frontend && npx tsc --noEmit && npx tsc -p e2e --noEmit && npx vitest run 2>&1 | tail -4 && npm run build 2>&1 | tail -3`
Expected: no type errors; all unit tests pass; the build writes `../backend/codetortoise/web/static`.

Run (from `frontend/`): `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --reporter=line 2>&1 | tail -15; rm -rf ../.pwtmp`
Expected: all pass. The single-workspace servers behave as before: one Perforce server, so no picker; the owner's Health link goes to `/workspaces/1`; the account menu shows `demo`.

- [ ] **Step 11: Commit**

```bash
cd frontend
git add src/api.ts src/api.test.ts src/viewer.ts src/viewer.test.ts src/lib/signin.ts src/lib/signin.test.ts \
  src/lib/reviewFilter.ts src/lib/reviewFilter.test.ts src/components/SignInForm.tsx src/pages/Login.tsx src/App.tsx \
  src/pages/Health.tsx src/pages/Reviews.tsx src/workspace/useReview.ts src/workspace/Workspace.tsx src/components/SinkMark.tsx \
  src/components/Comments.tsx src/workspace/FindingBody.tsx src/workspace/ClPage.tsx src/workspace/ReviewMenu.tsx \
  src/styles.css src/workspace/workspace.css e2e/landing.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-sinks.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(ui): sign-in per Perforce server — the picker, the account menu, the in-place prompt, the viewer inside a review, Health per workspace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 9: The Workspaces page, and Reviews by workspace

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/lib/workspaceForm.ts`, `frontend/src/lib/workspaceForm.test.ts`
- Modify: `frontend/src/lib/reviewFilter.ts`, `frontend/src/lib/reviewFilter.test.ts`
- Create: `frontend/src/pages/Workspaces.tsx`
- Modify: `frontend/src/pages/Reviews.tsx`, `frontend/src/App.tsx`, `frontend/src/board/prefs.ts`, `frontend/src/styles.css`
- Modify: `frontend/e2e/landing.spec.ts` (the phone menu's link)

**Interfaces:**
- Consumes: Task 8's `WorkspaceRow`, `WorkspaceFields`, `HealthCheck`, `useMe`, `Who`, `api.workspaces()`, `api.rebuildIndex(wid)`, `api.createReview(cls, title?, workspace_id?)`; Task 6's `POST /api/workspaces` and `PUT /api/workspaces/{id}` (→ the row plus `checks`), `DELETE /api/workspaces/{id}`, `POST /api/workspaces/detect {root}` → `{root, p4port, client, p4user, compile_commands: [paths], client_root, notes}`.
- Produces:
  - `api.ts`: `interface Detected`; `api.addWorkspace(body: WorkspaceFields)`, `api.editWorkspace(wid, body)`, `api.removeWorkspace(wid)`, `api.detect(root)`.
  - `lib/workspaceForm.ts`: `interface FormState` (every field a string, `vcs: "p4" | "git"`), `EMPTY`, `formErrors(f) -> Partial<Record<keyof FormState, string>>`, `withDetected(f, d)`, `fromFields(w)`, `toBody(f) -> WorkspaceFields`.
  - `lib/reviewFilter.ts`: `filterReviews(rows, query, chip, who, ws: number | null = null)`, `chipCounts(rows, who, ws = null)`, `workspaceChips(rows) -> {id, name, count}[]` (none unless the rows come from several workspaces), `pickOrder(owned, last)`.
  - `board/prefs.ts`: `keys.lastWorkspace = "ct.lastWorkspace"`.
  - `/workspaces` (the Workspaces page); the top bar's owner link is `Workspaces`; `/health` goes to the only owned workspace's Health page, else to `/workspaces`.
  - Copy: the Workspaces page's heading `Workspaces`, button `Add workspace`, form `Add workspace` with labels `Name`, `Version control`, `Perforce server (P4PORT)`, `Client`, `User`, `Root on this host` (button `Fill from root`), `Compile database`, `Swarm URL`, and under `Advanced`: `Build root`, `Settings`; buttons `Add` / `Save` / `Cancel`; per row `Health`, `Rebuild index`, `Edit`, `Remove`; the seed's row says `set in tortoise.yaml`; after a save, `<name> is ready.` or `<name> is saved but not ready: <reason>. …`, and `Sign in to <server>` when the session has no sign-in there. New review's picker is labelled `Workspace`; the workspace chips' group is labelled `Filter by workspace`.

- [ ] **Step 1: Write the failing unit tests**

Create `frontend/src/lib/workspaceForm.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { EMPTY, formErrors, fromFields, toBody, withDetected } from "./workspaceForm";

const OK = { ...EMPTY, name: "dsp", vcs: "git" as const, p4user: "amy", root: "/work/dsp" };
const FOUND = { root: "/work/dsp", p4port: "ssl:p4:1666", client: "amy-dsp", p4user: "amy",
                compile_commands: ["/work/dsp/build/compile_commands.json"], client_root: "/work/dsp", notes: [] };

describe("the Workspaces page's form (spec 2026-10-31 §9)", () => {
  it("can send a git workspace with a name, a user and a full root", () => {
    expect(formErrors(OK)).toEqual({});
  });

  it("says, by field, what the server would refuse", () => {
    expect(Object.keys(formErrors(EMPTY)).sort()).toEqual(["client", "name", "p4port", "p4user", "root"]);
    expect(formErrors({ ...OK, name: "a/b" }).name).toBe("1–40 characters, no /");
    expect(formErrors({ ...OK, name: "x".repeat(41) }).name).toBe("1–40 characters, no /");
    expect(formErrors({ ...OK, name: "x".repeat(40) }).name).toBeUndefined();
    expect(formErrors({ ...OK, root: "work/dsp" }).root).toBe("A full path on this host");
    expect(formErrors({ ...OK, vcs: "p4", p4port: "ssl:p4:1666" })).toEqual({ client: "A Perforce workspace needs its client" });
  });

  it("fills from the root what is still empty, and keeps what was typed", () => {
    expect(withDetected({ ...EMPTY, root: "/work/dsp/" }, FOUND)).toEqual({ ...EMPTY, name: "dsp", root: "/work/dsp",
      p4port: "ssl:p4:1666", client: "amy-dsp", p4user: "amy", compile_commands: "/work/dsp/build/compile_commands.json" });
    const typed = withDetected({ ...OK, name: "mine", p4user: "bob", compile_commands: "/elsewhere/compile_commands.json" }, FOUND);
    expect([typed.name, typed.p4user, typed.compile_commands, typed.vcs]).toEqual(["mine", "bob", "/elsewhere/compile_commands.json", "p4"]);
    expect(withDetected(OK, { ...FOUND, p4port: null, client: null, p4user: null, compile_commands: [] })).toEqual(OK);
  });

  it("sends blanks as unset and a blank compile database as auto; an edit starts from what is stored", () => {
    expect(toBody({ ...OK, name: " dsp ", swarm_url: "  ", compile_commands: " " })).toEqual({
      name: "dsp", vcs: "git", p4port: null, client: null, p4user: "amy", root: "/work/dsp", compile_commands: "auto",
      build_root: null, swarm_url: null, settings: "" });
    const stored = toBody({ ...OK, p4port: "second:1666", settings: "analysis: {sink_threshold: 3}" });
    expect(fromFields(stored)).toEqual({ ...OK, p4port: "second:1666", settings: "analysis: {sink_threshold: 3}" });
  });
});
```

In `frontend/src/lib/reviewFilter.test.ts`, change the import to `import { chipCounts, filterReviews, highlight, pickOrder, workspaceChips } from "./reviewFilter";` and append:

```ts
describe("reviews from several workspaces (spec 2026-10-31 §9)", () => {
  const two = [...rows, row(5, "dsp one", [9], "done", "high", "amy", SECOND)];

  it("has a chip per workspace, with its count, only when the rows come from several", () => {
    expect(workspaceChips(rows)).toEqual([]);
    expect(workspaceChips(two)).toEqual([{ id: 2, name: "dsp", count: 1 }, { id: 1, name: "fw", count: 4 }]);
  });

  it("filters by the workspace chip and counts the other chips inside it", () => {
    expect(ids(filterReviews(two, "", "all", AMY, 2))).toEqual([5]);
    expect(ids(filterReviews(two, "", "high", AMY, 1))).toEqual([1, 2]);
    expect(chipCounts(two, AMY, 2)).toEqual({ all: 1, high: 1, running: 0, mine: 0 });
    expect(chipCounts(two, AMY)).toEqual({ all: 5, high: 3, running: 2, mine: 2 });
  });

  it("lists New review's workspaces with the last used first, then by name", () => {
    const owned = [{ id: 1, name: "fw" }, { id: 2, name: "dsp" }, { id: 3, name: "sensor" }];
    expect(pickOrder(owned, 3).map((w) => w.id)).toEqual([3, 2, 1]);
    expect(pickOrder(owned, null).map((w) => w.id)).toEqual([2, 1, 3]);
    expect(pickOrder(owned, 99).map((w) => w.id)).toEqual([2, 1, 3]);           // a workspace removed since
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run 2>&1 | tail -20`
Expected: FAIL — `workspaceForm.test.ts` cannot import `./workspaceForm`; in `reviewFilter.test.ts`, `workspaceChips is not a function` and the workspace filter is ignored (`[1, 2, 3, 4, 5]` for workspace 2).

- [ ] **Step 3: Implement the form logic and the workspace chips**

In `frontend/src/api.ts`, after the `WorkspaceRow` interface add

```ts
/** What `codetortoise init` finds at a root (spec 2026-10-31 §8): P4CONFIG's server, client and user, the compile databases. */
export interface Detected {
  root: string; p4port: string | null; client: string | null; p4user: string | null; compile_commands: string[];
  client_root: string | null; notes: string[];
}
```

and in `api`, after the `workspaces` line add

```ts
  /** Saved even when its checks fail; the answer carries them (spec 2026-10-31 §11). */
  addWorkspace: (body: WorkspaceFields) => call<WorkspaceRow & { checks: HealthCheck[] }>("POST", "/api/workspaces", body),
  editWorkspace: (wid: number, body: WorkspaceFields) => call<WorkspaceRow & { checks: HealthCheck[] }>("PUT", `/api/workspaces/${wid}`, body),
  removeWorkspace: (wid: number) => call("DELETE", `/api/workspaces/${wid}`),
  detect: (root: string) => call<Detected>("POST", "/api/workspaces/detect", { root }),
```

Create `frontend/src/lib/workspaceForm.ts`:

```ts
/** The Workspaces page's add and edit form (spec 2026-10-31 §9) (pure): its fields as typed, what the server would refuse
 * (its own rules, spec §5 and §8), "Fill from root", and the body the server takes. */
import type { Detected, WorkspaceFields } from "../api";

export interface FormState {
  name: string; vcs: "p4" | "git"; p4port: string; client: string; p4user: string; root: string;
  compile_commands: string; build_root: string; swarm_url: string; settings: string;
}

export const EMPTY: FormState = { name: "", vcs: "p4", p4port: "", client: "", p4user: "", root: "", compile_commands: "auto",
                                  build_root: "", swarm_url: "", settings: "" };

/** What the server would refuse, by field; empty when the form can be sent. */
export function formErrors(f: FormState): Partial<Record<keyof FormState, string>> {
  const out: Partial<Record<keyof FormState, string>> = {};
  const name = f.name.trim();
  if (!name || [...name].length > 40 || name.includes("/")) out.name = "1–40 characters, no /";
  if (!f.root.trim().startsWith("/")) out.root = "A full path on this host";
  if (!f.p4user.trim()) out.p4user = "The Perforce user its reads run as";
  if (f.vcs === "p4" && !f.p4port.trim()) out.p4port = "A Perforce workspace needs its server";
  if (f.vcs === "p4" && !f.client.trim()) out.client = "A Perforce workspace needs its client";
  return out;
}

/** The form after "Fill from root": what was found fills the fields still empty (the name from the root's folder), the root
 * as found, the compile databases found in place of "auto"; a typed value stays. */
export function withDetected(f: FormState, d: Detected): FormState {
  const keep = (now: string, found: string | null | undefined) => (now.trim() ? now : found ?? now);
  const cc = f.compile_commands.trim();
  return {
    ...f,
    root: d.root || f.root,
    name: keep(f.name, d.root.split("/").filter(Boolean).at(-1)),
    vcs: d.p4port ? "p4" : f.vcs,
    p4port: keep(f.p4port, d.p4port), client: keep(f.client, d.client), p4user: keep(f.p4user, d.p4user),
    compile_commands: (!cc || cc === "auto") && d.compile_commands.length ? d.compile_commands.join("\n") : f.compile_commands,
  };
}

/** A stored workspace, to edit. */
export function fromFields(w: WorkspaceFields): FormState {
  return { name: w.name, vcs: w.vcs, p4port: w.p4port ?? "", client: w.client ?? "", p4user: w.p4user, root: w.root,
           compile_commands: w.compile_commands, build_root: w.build_root ?? "", swarm_url: w.swarm_url ?? "", settings: w.settings };
}

/** The body the server takes: blanks unset, a blank compile database "auto". */
export function toBody(f: FormState): WorkspaceFields {
  const opt = (v: string) => v.trim() || null;
  return { name: f.name.trim(), vcs: f.vcs, p4port: opt(f.p4port), client: opt(f.client), p4user: f.p4user.trim(),
           root: f.root.trim(), compile_commands: f.compile_commands.trim() || "auto", build_root: opt(f.build_root),
           swarm_url: opt(f.swarm_url), settings: f.settings };
}
```

In `frontend/src/lib/reviewFilter.ts`, replace `filterReviews` and `chipCounts` with:

```ts
/** Rows matching every word of the query (title, CL number, author, status), the chip, and the workspace chip (null: any). */
export function filterReviews(rows: ReviewRow[], query: string, chip: Chip, who: Who, ws: number | null = null): ReviewRow[] {
  const qs = words(query.replace(/\bcl\s+(\d+)/gi, "cl$1"));
  return rows.filter((r) => (ws === null || r.workspace?.id === ws) && chipOk(r, chip, who) && qs.every((w) => haystack(r).includes(w)));
}

/** Each chip's count among the rows of the workspace chip pressed (null: all rows). */
export function chipCounts(rows: ReviewRow[], who: Who, ws: number | null = null): Record<Chip, number> {
  const pool = ws === null ? rows : rows.filter((r) => r.workspace?.id === ws);
  const n = (c: Chip) => pool.filter((r) => chipOk(r, c, who)).length;
  return { all: n("all"), high: n("high"), running: n("running"), mine: n("mine") };
}

/** A chip per workspace the rows come from, by name, with its count (spec 2026-10-31 §9); none when they all come from one. */
export function workspaceChips(rows: ReviewRow[]): { id: number; name: string; count: number }[] {
  const by = new Map<number, { id: number; name: string; count: number }>();
  for (const r of rows) {
    if (!r.workspace) continue;
    const c = by.get(r.workspace.id) ?? { id: r.workspace.id, name: r.workspace.name, count: 0 };
    c.count++;
    by.set(c.id, c);
  }
  return by.size > 1 ? [...by.values()].sort((a, b) => a.name.localeCompare(b.name)) : [];
}

/** New review's workspaces (spec 2026-10-31 §9): the last used first, then by name. */
export function pickOrder<T extends { id: number; name: string }>(owned: T[], last: number | null): T[] {
  return [...owned].sort((a, b) => Number(b.id === last) - Number(a.id === last) || a.name.localeCompare(b.name));
}
```

- [ ] **Step 4: Run the unit tests**

Run: `cd frontend && npx vitest run 2>&1 | tail -5`
Expected: all pass.

- [ ] **Step 5: The Workspaces page**

In `frontend/src/board/prefs.ts`, add to `keys` after `shortcuts`:

```ts
  /** The workspace New review last started a review in: its picker lists it first (spec 2026-10-31 §9). */
  lastWorkspace: "ct.lastWorkspace",
```

Create `frontend/src/pages/Workspaces.tsx`:

```tsx
import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText, type HealthCheck, type WorkspaceFields, type WorkspaceRow } from "../api";
import { useMe } from "../App";
import { EMPTY, type FormState, formErrors, fromFields, toBody, withDetected } from "../lib/workspaceForm";

type Checked = WorkspaceRow & { checks: HealthCheck[] };

/** The Workspaces page (spec 2026-10-31 §9): the workspaces on the session's servers with their status; an owner adds one
 * (saved even when its checks fail, §11) and edits, removes, rebuilds the index of and opens the Health page of their own. */
export default function Workspaces() {
  const me = useMe();
  const [rows, setRows] = useState<WorkspaceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | "new" | null>(null);          // the workspace whose form is open, or a new one
  const [saved, setSaved] = useState<Checked | null>(null);               // what the last add or edit answered
  const load = () => api.workspaces().then((w) => { setRows(w); setError(null); })
    .catch((e) => setError(errorText(e, "The workspaces could not be loaded.")));
  useEffect(() => { load(); }, []);
  const done = (w: Checked) => { setSaved(w); setOpen(null); load(); };
  const edit = (to: number | "new") => { setSaved(null); setOpen(to); };

  return (
    <main className="page">
      <div className="wsp-head">
        <h1>Workspaces</h1>
        {!!me?.owner_of.length && open !== "new" && <button onClick={() => edit("new")}>Add workspace</button>}
      </div>
      {saved && <SavedNote w={saved} signedIn={!!me?.logins.some((l) => l.server === saved.server)} />}
      {open === "new" && <WorkspaceForm initial={EMPTY} verb="Add" submit={api.addWorkspace} onDone={done} onCancel={() => setOpen(null)} />}
      {error && <p className="error" role="alert">{error}</p>}
      {!rows && !error && <p className="muted">Loading…</p>}
      <ul className="wsp-list">
        {rows?.map((w) => (
          <li key={w.id} className="wsp-row">
            <div className="wsp-main">
              <b>{w.name}</b>
              <span className="muted small">{w.server}{w.client ? ` · ${w.client}` : ""}</span>
              <span className={`hc-pill ${w.ready ? "ok" : "bad"}`}>● {w.ready ? "ready" : "not ready"}</span>
              {w.seed && <span className="muted small">set in tortoise.yaml</span>}
            </div>
            {!w.ready && w.reason && <div className="wsp-reason mono small">{w.reason}</div>}
            {w.is_owner && <Actions w={w} onEdit={() => edit(w.id)} onChanged={load} />}
            {open === w.id && w.fields && (
              <WorkspaceForm initial={fromFields(w.fields)} verb="Save" submit={(body) => api.editWorkspace(w.id, body)} onDone={done}
                             onCancel={() => setOpen(null)} />
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}

/** What an add or an edit answered (§11: saved even when its checks fail), and the sign-in its server still needs. */
function SavedNote({ w, signedIn }: { w: Checked; signedIn: boolean }) {
  const failed = w.checks.filter((c) => c.hard && !c.ok);
  return (
    <div className={`banner wsp-saved${w.ready ? "" : " warn"}`} role="status">
      {w.ready ? `${w.name} is ready.`
        : `${w.name} is saved but not ready: ${w.reason}. Fix it on this host, then press Recheck on its Health page.`}
      {failed.length > 0 && <ul className="small">{failed.map((c) => <li key={c.name}><b>{c.name}</b>: {c.detail}</li>)}</ul>}
      {!signedIn && (
        <p><Link to={`/login?server=${encodeURIComponent(w.server)}&next=/workspaces`}>Sign in to {w.server}</Link> to see it and
          start reviews in it.</p>
      )}
    </div>
  );
}

/** An owner's tools on one workspace: its Health page and Rebuild index, and for one added here, Edit and Remove. */
function Actions({ w, onEdit, onChanged }: { w: WorkspaceRow; onEdit: () => void; onChanged: () => void }) {
  const [msg, setMsg] = useState<{ text: string; failed?: boolean } | null>(null);
  const run = (act: () => Promise<unknown>, ok: string | null, failed: string) => {   // a new press clears the last answer
    setMsg(null);
    act().then(() => { if (ok) setMsg({ text: ok }); onChanged(); }).catch((e) => setMsg({ text: errorText(e, failed), failed: true }));
  };
  const remove = () => {
    if (window.confirm(`Remove the workspace ${w.name}? Its symbol index and settings are deleted.`))
      run(() => api.removeWorkspace(w.id), null, "The workspace could not be removed.");
  };
  return (
    <div className="wsp-acts">
      <Link to={`/workspaces/${w.id}`}>Health</Link>
      <button onClick={() => run(() => api.rebuildIndex(w.id), "Index rebuild queued", "The index rebuild could not be queued.")}>
        Rebuild index</button>
      {!w.seed && <button onClick={onEdit}>Edit</button>}
      {!w.seed && <button onClick={remove}>Remove</button>}
      {msg && <span className={msg.failed ? "error" : "muted"} role={msg.failed ? "alert" : "status"}>{msg.text}</span>}
    </div>
  );
}

/** Add or edit a workspace (spec 2026-10-31 §9): what the server would refuse shows once Add or Save is pressed. */
function WorkspaceForm({ initial, verb, submit, onDone, onCancel }: {
  initial: FormState; verb: "Add" | "Save"; submit: (body: WorkspaceFields) => Promise<Checked>; onDone: (w: Checked) => void;
  onCancel: () => void;
}) {
  const [f, setF] = useState(initial);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);              // what "Fill from root" could not read
  const errs = formErrors(f);
  const set = (k: keyof FormState) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const v = e.target.value;
    setF((now) => ({ ...now, [k]: v }));
  };
  const fill = () => {
    setError(null);
    api.detect(f.root.trim()).then((d) => { setF((now) => withDetected(now, d)); setNotes(d.notes); })
      .catch((e) => setError(errorText(e, "Nothing could be read at that root.")));
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await submit(toBody(f)));
    } catch (err) {
      setError(errorText(err, "The workspace could not be saved."));
      setBusy(false);
    }
  }
  const bad = (k: keyof FormState) => (tried && errs[k] ? <div className="wsp-bad">{errs[k]}</div> : null);
  const text = (k: keyof FormState, label: string) => (
    <>
      <label>{label}<input value={f[k]} onChange={set(k)} aria-invalid={tried && !!errs[k]} /></label>
      {bad(k)}
    </>
  );

  return (
    <form className="card stack wsp-form" onSubmit={save} aria-label={verb === "Add" ? "Add workspace" : `Edit ${initial.name}`}>
      {text("name", "Name")}
      <label>Version control
        <select value={f.vcs} onChange={set("vcs")}><option value="p4">Perforce</option><option value="git">Git</option></select>
      </label>
      {text("p4port", "Perforce server (P4PORT)")}
      {text("client", "Client")}
      {text("p4user", "User")}
      <div className="hint">The Perforce user its reads run as. Whoever signs in to its server as this user owns it.</div>
      <div className="wsp-root">
        <label>Root on this host<input value={f.root} onChange={set("root")} aria-invalid={tried && !!errs.root} /></label>
        <button type="button" onClick={fill} disabled={!f.root.trim().startsWith("/")}>Fill from root</button>
      </div>
      {bad("root")}
      {notes.map((n) => <div key={n} className="hint">{n}</div>)}
      <label>Compile database<textarea rows={2} value={f.compile_commands} onChange={set("compile_commands")} /></label>
      <div className="hint">auto, or the path of a compile_commands.json (one per line for several)</div>
      {text("swarm_url", "Swarm URL")}
      <details className="wsp-adv">
        <summary>Advanced</summary>
        <div className="stack">
          {text("build_root", "Build root")}
          <label>Settings<textarea rows={8} value={f.settings} onChange={set("settings")} spellCheck={false} /></label>
          <div className="hint">tortoise.yaml's toolchain, targets and analysis keys, as YAML</div>
        </div>
      </details>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="wsp-btns">
        <button className="go" disabled={busy}>{busy ? "Checking…" : verb}</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
```

- [ ] **Step 6: Reviews by workspace, New review's picker, the top bar's Workspaces link**

Replace `frontend/src/pages/Reviews.tsx` with:

```tsx
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorText, type ReviewRow, type WorkspaceRow } from "../api";
import { useMe } from "../App";
import { keys, load as loadPref, save as savePref } from "../board/prefs";
import HeadlinePill from "../components/HeadlinePill";
import Logo from "../components/Logo";
import { ago, type Chip, chipCounts, filterReviews, highlight, parseCls, pickOrder, workspaceChips } from "../lib/reviewFilter";

const CHIPS: [Chip, string][] = [["all", "All"], ["high", "High risk"], ["running", "Running"], ["mine", "Mine"]];
const RISK_DOT: Record<string, string> = { high: "#ff4d6d", medium: "#ffb020", low: "#16a34a" };   // same as the risk pills
const LIVE = new Set(["queued", "running"]);

/** Landing page (spec §12): start a review on the left (owner), searchable reviews on the right. With reviews from several
 * workspaces, each row names its workspace and chips filter by workspace (spec 2026-10-31 §9). */
export default function Reviews() {
  const me = useMe();
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [chip, setChip] = useState<Chip>("all");
  const [ws, setWs] = useState<number | null>(null);                     // the workspace chip pressed, if any
  const [owned, setOwned] = useState<WorkspaceRow[] | null>(null);        // New review's workspaces, the last used first
  const owner = !!me?.owner_of.length;                                   // owns a workspace: starts reviews (spec 2026-10-31 §7)

  useEffect(() => {
    let stop = false;
    const load = () => api.reviews().then((r) => { if (!stop) setRows(r); }).catch((e) => setError(errorText(e, "The reviews could not be loaded.")));
    load();
    return () => { stop = true; };
  }, []);
  useEffect(() => {
    if (!owner) return;
    api.workspaces().then((all) => setOwned(pickOrder(all.filter((w) => w.is_owner), loadPref<number | null>(keys.lastWorkspace, null))))
      .catch(() => setOwned([]));                          // the server then takes the only one, or says to choose
  }, [owner]);
  const live = !!rows?.some((r) => LIVE.has(r.status));
  useEffect(() => {                                       // keep running reviews fresh without a reload
    if (!live) return;
    const t = window.setInterval(() => api.reviews().then(setRows).catch(() => {}), 5000);
    return () => window.clearInterval(t);
  }, [live]);

  const who = useMemo(() => Object.fromEntries((me?.logins ?? []).map((l) => [l.server, l.user])), [me]);
  const wsChips = useMemo(() => workspaceChips(rows ?? []), [rows]);
  const wsOn = wsChips.some((c) => c.id === ws) ? ws : null;             // a chip that went away filters nothing
  const shown = useMemo(() => (rows ? filterReviews(rows, query, chip, who, wsOn) : []), [rows, query, chip, who, wsOn]);
  const counts = useMemo(() => chipCounts(rows ?? [], who, wsOn), [rows, who, wsOn]);

  return (
    <main className="home-page">
      <section className="rv-hello">
        {me && owner ? <StartReview owned={owned} only={me.owner_of.length === 1 ? me.owner_of[0] : undefined} /> : (
          <>
            <Logo size={72} />
            <h1>Hi {[...new Set((me?.logins ?? []).map((l) => l.user))].join(", ")}</h1>
            <p>These are the reviews shared on this CodeTortoise. Open one to explore its call flows, side effects and
              changed code, and leave comments where you see something.</p>
          </>
        )}
      </section>
      <section className="rv-main">
        <div className="rv-head">
          <h2>Reviews</h2>
          <label className="rv-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" aria-label="Search reviews" placeholder="Search title, CL, author or status" value={query}
                   onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); }} />
          </label>
        </div>
        <div className="rv-chips">
          {CHIPS.map(([c, label]) => (
            <button key={c} className={chip === c ? "on" : ""} aria-pressed={chip === c} onClick={() => setChip(c)}>
              {label} <span>{counts[c]}</span>
            </button>
          ))}
        </div>
        {wsChips.length > 0 && (
          <div className="rv-chips" role="group" aria-label="Filter by workspace">
            {wsChips.map((c) => (
              <button key={c.id} className={wsOn === c.id ? "on" : ""} aria-pressed={wsOn === c.id} onClick={() => setWs(wsOn === c.id ? null : c.id)}>
                {c.name} <span>{c.count}</span>
              </button>
            ))}
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        {!rows && !error && <p className="muted">Loading…</p>}
        {rows && rows.length === 0 && <p className="muted rv-empty">No reviews yet{owner ? " — start one on the left." : "."}</p>}
        <div className="rv-list">
          {shown.map((r) => (
            <Link key={r.id} to={`/r/${r.id}`} className="rv-row">
              <span className="dot" style={{ background: r.risk ? RISK_DOT[r.risk] : "var(--line)" }} />
              <b>{highlight(r.title, query).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</b>
              {wsChips.length > 0 && r.workspace && <span className="rv-ws">{r.workspace.name}</span>}
              <span className="cls">{r.cls.map((c) => <span key={c} className="cl">{c}</span>)}</span>
              <span className="sp" />
              {r.headline ? <HeadlinePill h={r.headline} className="rv-headline" />
                : r.risk && <span className={`rv-risk ${r.risk}`}>{r.risk.toUpperCase()}</span>}
              <span className={`rv-status ${r.status}`}>{LIVE.has(r.status) ? `${r.status}…` : r.status}</span>
              <span className="when">{ago(r.created_at)} · {r.created_by}</span>
            </Link>
          ))}
        </div>
        {rows && rows.length > 0 && (query || chip !== "all" || wsOn !== null) && (
          <p className="rv-count">{shown.length} of {rows.length} reviews{query ? " · Esc clears" : ""}</p>
        )}
      </section>
    </main>
  );
}

/** New review (spec 2026-10-31 §9): with several workspaces owned, a picker of them (the last used first); `only`: the one
 * workspace owned, while the list loads. */
function StartReview({ owned, only }: { owned: WorkspaceRow[] | null; only?: number }) {
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const cls = parseCls(text);
  const choices = owned ?? [];
  const target = choices.length > 1 ? picked ?? choices[0].id : choices[0]?.id ?? only;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);                                // a new attempt clears the last refusal, so a repeat is told again
    try {
      const r = await api.createReview(cls, title.trim() || undefined, target);
      if (target !== undefined) savePref(keys.lastWorkspace, target);
      navigate(`/r/${r.id}`);
    } catch (err) {
      setError(errorText(err, "The review could not be started."));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <Logo size={72} />
      <h1>Review a change</h1>
      <p>Shelved or submitted changelists, one or several; they're stacked in CL order.</p>
      {choices.length > 1 && (
        <>
          <label htmlFor="rv-workspace">Workspace</label>
          <select id="rv-workspace" value={target} onChange={(e) => setPicked(Number(e.target.value))}>
            {choices.map((w) => <option key={w.id} value={w.id}>{w.name}{w.ready ? "" : " (not ready)"}</option>)}
          </select>
        </>
      )}
      <label>Changelists (shelved or submitted)
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="12345 12346" />
      </label>
      <div className="hint">{cls.length ? `Will analyse: ${cls.join(", ")}` : "Enter one or more CL numbers."}</div>
      <label>Title (optional)<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      {error && <div className="err" role="alert">{error}</div>}
      <button className="go" disabled={!cls.length || busy}>{busy ? "Starting…" : "Start review"}</button>
      <div className="hint">The board opens on its own when the analysis finishes.</div>
    </form>
  );
}
```

In `frontend/src/App.tsx`: add `import Workspaces from "./pages/Workspaces";` after `import Reviews from "./pages/Reviews";`; replace `ToHealth` with

```tsx
/** `/health` was the one workspace's Health page (spec 2026-10-31 §8): the owner of one workspace gets its Health page, the
 * owner of several the Workspaces page. */
function ToHealth() {
  const owned = useMe()?.owner_of ?? [];
  return <Navigate to={owned.length === 1 ? `/workspaces/${owned[0]}` : owned.length ? "/workspaces" : "/"} replace />;
}
```

replace `{me.owner_of.length > 0 && <Link to="/health">Health</Link>}` with `{me.owner_of.length > 0 && <Link to="/workspaces">Workspaces</Link>}`, and add `<Route path="/workspaces" element={<Workspaces />} />` before the `/workspaces/:id` route.

In `frontend/src/styles.css`, change the selector `.rv-hello textarea, .rv-hello input {` to `.rv-hello textarea, .rv-hello input, .rv-hello select {` and add after that rule (it ends with `color-scheme: dark; }`)

```css
.rv-hello select option { color: var(--ink); background: var(--surface); }   /* the open list is drawn on the page's colours */
```

after the `.rv-row .when { … }` line add

```css
.rv-row .rv-ws { font-size: 11.5px; font-weight: 600; padding: 1px 8px; border-radius: 99px; color: var(--muted); background: var(--gap-bg); }
```

and after the `.hc-cards { … }` line add

```css
/* ---- workspaces (spec 2026-10-31 §9) ---- */
.wsp-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; }
.wsp-head h1 { margin: 0; }
.wsp-list { list-style: none; padding: 0; margin: 16px 0; display: flex; flex-direction: column; gap: 10px; }
.wsp-row { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; }
.wsp-main { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; }
.wsp-main .muted, .wsp-reason { overflow-wrap: anywhere; }
.wsp-reason { color: var(--muted); margin-top: 4px; }
.wsp-acts { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin-top: 10px; }
.wsp-form { max-width: 640px; }
.wsp-form .hint, .wsp-form .wsp-bad { font-size: 12px; margin-top: -8px; }
.wsp-form .hint { color: var(--muted); overflow-wrap: anywhere; }
.wsp-form .wsp-bad { color: var(--bad); }
.wsp-form textarea { font: 12.5px/1.45 var(--mono); }
.wsp-root { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }
.wsp-root label { flex: 1; min-width: 220px; }
.wsp-adv summary { cursor: pointer; color: var(--muted); }
.wsp-adv > .stack { margin-top: 10px; }
.wsp-btns { display: flex; gap: 8px; }
.wsp-saved ul { margin: 6px 0 0; padding-left: 18px; }
.wsp-saved p { margin: 6px 0 0; }
```

In `frontend/e2e/landing.spec.ts`, the phone test's five Health lines become:

```ts
    await expect(page.getByRole("link", { name: "Workspaces" })).toBeHidden();
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("link", { name: "Workspaces" })).toBeVisible();
    await page.getByRole("link", { name: "Workspaces" }).click();
    await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
```

- [ ] **Step 7: Type-check, unit tests, build, then the whole end-to-end suite**

Run: `cd frontend && npx tsc --noEmit && npx tsc -p e2e --noEmit && npx vitest run 2>&1 | tail -4 && npm run build 2>&1 | tail -3`
Expected: no type errors; all unit tests pass; the build succeeds.

Run (from `frontend/`): `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --reporter=line 2>&1 | tail -15; rm -rf ../.pwtmp`
Expected: all pass. On the single-workspace servers New review has no picker (one workspace owned) and rows show no workspace names (one workspace).

- [ ] **Step 8: Commit**

```bash
cd frontend
git add src/api.ts src/lib/workspaceForm.ts src/lib/workspaceForm.test.ts src/lib/reviewFilter.ts src/lib/reviewFilter.test.ts \
  src/pages/Workspaces.tsx src/pages/Reviews.tsx src/App.tsx src/board/prefs.ts src/styles.css e2e/landing.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(ui): the Workspaces page — add with Fill from root, edit, remove, rebuild, Health; reviews by workspace and New review's picker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 10: End to end — one server, two workspaces

**Files:**
- Create: `frontend/e2e/serve-multi.sh`, `frontend/e2e/multi-workspace.spec.ts`
- Modify: `frontend/e2e/helpers.ts`, `frontend/playwright.config.ts`

**Interfaces:**
- Consumes: `fixture-demo --dir D --port P` (writes `D/tortoise.yaml` with the git fixture at `D/ws` as the seed, owner `demo`, `auth: dev`); Task 6's `GET /api/workspaces` (the owner's rows carry `fields.root`); Tasks 8–9's copy: the sign-in form (`Perforce server`, `P4 user`, `Sign in`, `Sign in to <server> to open this review`), the top bar's `Workspaces` link and account menu (`.topbar .account`, lines `<server> as <user>`), the Workspaces page (`Add workspace`, the form `Add workspace` and its labels, `Fill from root`, `Add`, `.wsp-saved`, `Sign in to <server>`, `.wsp-row b`), New review's `Workspace` picker, the `Filter by workspace` chips, `.rv-row .rv-ws`, the review header's `.ws-where`, the CL page heading `CL <n> · …`; helpers `login(page)` and `railReady(page)`.
- Produces: `MULTI = "http://127.0.0.1:8793"` in `e2e/helpers.ts`; a server on port 8793 with the seed `ws` on `local` and an unregistered second copy of the fixture at `<dir>/second/ws`.

- [ ] **Step 1: The two-workspace server**

Create `frontend/e2e/serve-multi.sh`:

```bash
#!/usr/bin/env bash
# Starts one CodeTortoise for two workspaces (spec 2026-10-31 §13): the bundled fixture as the seed (`ws`, on `local`), and
# a second copy of it at $DIR/second/ws, which e2e/multi-workspace.spec.ts adds on the Workspaces page as `second`,
# labelled with a second Perforce server (second:1666). Only the seed is in tortoise.yaml.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8793 >/dev/null
$CMD fixture-demo --dir "$DIR/second" --port 8793 >/dev/null      # its own tortoise.yaml goes unused
exec $CMD serve --config "$DIR/tortoise.yaml"
```

Run: `chmod +x frontend/e2e/serve-multi.sh` (from the repository root).

In `frontend/playwright.config.ts`, after the `serve-sinks.sh` entry add:

```ts
    // one server, two workspaces (e2e/multi-workspace.spec.ts): the fixture as the seed, a second copy to add in the UI
    { command: "bash e2e/serve-multi.sh", url: "http://127.0.0.1:8793/api/me", timeout: 120_000, reuseExistingServer: false },
```

In `frontend/e2e/helpers.ts`, after the `SINKS` constant add:

```ts
/** One server for two workspaces (e2e/serve-multi.sh): the fixture as `ws` on `local`; e2e/multi-workspace.spec.ts adds a
 * second copy as `second` on second:1666. */
export const MULTI = "http://127.0.0.1:8793";
```

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/multi-workspace.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { login, MULTI, railReady } from "./helpers";

/** One server, two workspaces (spec 2026-10-31 §13): the owner adds the second copy of the fixture on the Workspaces page,
 * labelled with a second Perforce server, signs in there, reviews in both workspaces and sees both on the list; a link to
 * the review on the second server then signs in from its prompt. The tests run in order: the second uses the first's
 * review. */
test.describe.serial("one server, two workspaces", () => {
  test.use({ baseURL: MULTI });
  let deep = "";                                         // a CL page of the review in `second`

  test("an owner adds a workspace on a second server, signs in there and reviews in both; the list shows both", async ({ page }) => {
    test.setTimeout(240_000);                            // a workspace's checks, then two reviews
    await login(page);
    const [seed] = await (await page.request.get("/api/workspaces")).json();
    const root = (seed.fields.root as string).replace(/\/ws$/, "/second/ws");

    await page.getByRole("link", { name: "Workspaces" }).click();
    await page.getByRole("button", { name: "Add workspace" }).click();
    const form = page.getByRole("form", { name: "Add workspace" });
    await form.getByLabel("Name", { exact: true }).fill("second");   // first: Fill from root would name it after the folder, ws
    await form.getByLabel("Version control").selectOption("git");
    await form.getByLabel("Perforce server (P4PORT)").fill("second:1666");
    await form.getByLabel("User", { exact: true }).fill("demo");
    await form.getByLabel("Root on this host").fill(root);
    await form.getByRole("button", { name: "Fill from root" }).click();
    await expect(form.getByLabel("Compile database")).toHaveValue(`${root}/compile_commands.json`);
    await form.getByRole("button", { name: "Add", exact: true }).click();
    const saved = page.locator(".wsp-saved");
    await expect(saved).toContainText("second is ready.", { timeout: 60_000 });

    // the session has no sign-in on second:1666 yet, so the list leaves `second` out and the note offers the sign-in
    await saved.getByRole("link", { name: "Sign in to second:1666" }).click();
    await expect(page.getByLabel("Perforce server")).toHaveValue("second:1666");
    await page.getByLabel("P4 user").fill("demo");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
    await expect(page.locator(".wsp-row b")).toHaveText(["second", "ws"]);

    for (const name of ["ws", "second"]) {
      await page.getByRole("link", { name: "Reviews" }).first().click();
      await page.getByLabel("Workspace", { exact: true }).selectOption({ label: name });
      await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
      await page.getByRole("button", { name: "Start review" }).click();
      await railReady(page);
      await expect(page.locator(".ws-where")).toHaveText(name);
    }
    deep = `${page.url().match(/\/r\/\d+/)![0]}/cl/102`;

    await page.getByRole("link", { name: "Reviews" }).first().click();
    const rows = page.locator(".rv-row");
    await expect(rows).toHaveCount(2);
    await expect(rows.locator(".rv-ws")).toHaveText(["second", "ws"]);                        // the newest first
    await page.getByRole("group", { name: "Filter by workspace" }).getByRole("button", { name: /^second/ }).click();
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("second");

    await page.locator(".topbar .account summary").click();
    await expect(page.locator(".topbar .account")).toContainText("local as demo");
    await expect(page.locator(".topbar .account")).toContainText("second:1666 as demo");
  });

  test("a link to a review on the other server signs in from its prompt and opens where it pointed", async ({ page }) => {
    expect(deep, "the first test made the review").not.toBe("");
    await login(page);                                   // a new session: the picker starts on local, the first server
    await page.goto(deep);
    await expect(page.getByText("Sign in to second:1666 to open this review")).toBeVisible();
    await expect(page.getByLabel("Perforce server"), "the review names its server: no picker").toHaveCount(0);
    await page.getByLabel("P4 user").fill("demo");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: /^CL 102 · / })).toBeVisible({ timeout: 30_000 });
    expect(new URL(page.url()).pathname, "the same address, not the Reviews page").toBe(deep);
    await page.locator(".topbar .account summary").click();
    await expect(page.locator(".topbar .account")).toContainText("second:1666 as demo");
  });
});
```

- [ ] **Step 3: Type-check and run the spec**

Run: `cd frontend && npx tsc -p e2e --noEmit && npm run build 2>&1 | tail -2`
Expected: no type errors; the build succeeds.

Run (from `frontend/`): `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/multi-workspace.spec.ts --reporter=line 2>&1 | tail -15; rm -rf ../.pwtmp`
Expected: `2 passed`. These tests check what Tasks 5–9 built, so they pass on their first run; a failure is a defect in those tasks (debug it with superpowers:systematic-debugging), never a reason to loosen an assertion.

- [ ] **Step 4: Run the whole end-to-end suite**

Run (from `frontend/`): `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --reporter=line 2>&1 | tail -15; rm -rf ../.pwtmp`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/serve-multi.sh frontend/e2e/multi-workspace.spec.ts frontend/e2e/helpers.ts frontend/playwright.config.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test(e2e): one server, two workspaces — add one on a second server, review in both, open a link to the other server from its prompt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 11: README — one server for every workspace

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the behaviour of Tasks 1–10 as the spec states it (§4, §7, §9–§12); the copy of Tasks 8–9 (`Workspaces`, `Add workspace`, `Fill from root`, `Recheck`, `Perforce server`, `<server> as <user>`, `Sign in to another server`); Task 7's `--workspace NAME`.
- Produces: the README section `### 5. More workspaces on one server` (anchor `#5-more-workspaces-on-one-server`).

- [ ] **Step 1: Quick start and tortoise.yaml**

After the line that starts `Headless run, which prints the findings:` (end of the Quick start) add a blank line and:

```markdown
One server hosts any number of workspaces: the one in `tortoise.yaml` is the first, and its owner adds more on the
**Workspaces** page (see [More workspaces on one server](#5-more-workspaces-on-one-server)).
```

In `### 3. Write tortoise.yaml`, replace the paragraph

```markdown
`tortoise.yaml` tells CodeTortoise who owns it, which workspace to read, how your code is compiled and how to serve
the app. Relative paths are resolved against the folder that holds the file.
```

with

```markdown
`tortoise.yaml` tells CodeTortoise how to serve the app and, for its first workspace, who owns it, which workspace to
read and how your code is compiled. Relative paths are resolved against the folder that holds the file. More
workspaces are added in the app (see [More workspaces on one server](#5-more-workspaces-on-one-server)).
```

In `#### Every setting`, change the `data_dir` line to

```yaml
  data_dir: /var/lib/codetortoise   # SQLite database; workspaces/<id>/ holds each workspace's symbol index and toolchain cache
```

and after the `  vcs: p4` line under `workspace:` add

```yaml
  name: main                        # optional: its name in the app (default: the client's name; git: the root folder's name)
```

- [ ] **Step 2: Index, check, run — per workspace**

In `### 4. Index, check, run`, replace `Open the **Health** page as the owner.` with `Open **Workspaces**, then your workspace's **Health**, as the owner.`, and replace `Only the owner can start reviews.` with `Only a workspace's owner can start reviews in it.`

In the shared-sink paragraph above it, replace `a field's declaration note or the Health page; marks apply to every review from its next run.` with `a field's declaration note or the workspace's Health page; marks apply to every review of that workspace from its next run.`

- [ ] **Step 3: The new section**

Insert before `### Compile database`:

```markdown
### 5. More workspaces on one server

One `codetortoise serve` hosts reviews for any number of workspaces, on one Perforce server or several. The workspace in
`tortoise.yaml` is the first: its name is `workspace.name`, else the client's name (a git workspace: the root folder's
name), the app shows it as "set in tortoise.yaml", and it is edited only there. The file's `server`, `llm`, `auth` and
`analysis` apply to every workspace.

To add one, open **Workspaces** as the owner of any workspace and press **Add workspace**:

- **Name**, **Perforce server (P4PORT)**, **Client** and **User**. The user is who its Perforce reads run as, and its
  owner: whoever signs in to that Perforce server as that user owns the workspace, starts its reviews and opens its
  Health page.
- **Root on this host**: the synced workspace on this machine. **Fill from root** reads the server, client, user and
  compile databases found there, the way `codetortoise init` does.
- **Compile database** (`auto`, or one path per line), **Swarm URL**, and under **Advanced** a build root and the
  `toolchain`, `targets` and `analysis` keys of `tortoise.yaml`, as YAML (its `analysis` keys override the file's).

A workspace is saved even when its checks fail: it shows as not ready, with the reason, and once the host is fixed,
**Recheck** on its Health page runs the checks again. A workspace that isn't ready keeps its finished reviews readable
and refuses new reviews and re-runs until its checks pass. Each workspace has its own folder, `<data_dir>/workspaces/<id>/`,
with its symbol index and toolchain cache, and its own shared-sink marks and Swarm URL. An edit is refused while one of
its reviews runs, and a workspace can be removed only while it has no reviews.

Sign-in is per Perforce server. With workspaces on several servers, the sign-in page has a **Perforce server** picker,
and the menu under your name lists each sign-in ("`<server>` as `<user>`") with **Sign in to another server**. A link to
a review on a server you aren't signed in to asks you to sign in there, then opens the review.

On the command line, `index`, `review`, `stories-check` and `check-parse` take `--workspace NAME`; without it they use
the workspace in `tortoise.yaml`, or the only one there is. `serve` also starts from a file without a `workspace:`
section when its data folder already holds a workspace.

Upgrading a single-workspace server: the first start on its data folder gives the existing reviews and shared-sink marks
to the workspace in `tortoise.yaml`, ends the old sign-ins (everyone signs in again), and rebuilds that workspace's
symbol index once, in its new folder.
```

- [ ] **Step 4: Access and protections**

In `### Access and protections`, replace the first bullet's opening `Everything shown is read **as the owner**.` with `Everything shown is read **as the owner** of the review's workspace.`, and replace the second bullet (from `**Viewers see what the owner's workspace can see.**` to `contains only what that audience may read.`) with:

```markdown
- **Viewers see what the owner's workspace can see.** Anyone who can sign in to a Perforce server can open every
  review of every workspace on that server and fetch any synced file in those workspaces; a review on another server
  needs a sign-in on that server. Their own Perforce protections are not yet applied to what they read (per-file access
  is planned). If you host code that is restricted to a subset of users, run a separate instance per audience, or put it
  in a workspace on a Perforce server that only that audience can sign in to, with a view that contains only what that
  audience may read.
```

- [ ] **Step 5: Check the result**

Run: `grep -n "5-more-workspaces-on-one-server\|^### 5\. More workspaces\|Only the owner can start\|Open the \*\*Health\*\* page\|or the Health page; marks" README.md`
Expected: the two links and the heading (`### 5. More workspaces on one server`) only; the replaced sentences are gone.

Run: `git diff --stat README.md && git diff README.md | grep -nE "^\+.*(/home/|/media/|/Users/)" ; echo "exit $?"`
Expected: `README.md` changed; the grep finds no absolute local path (`exit 1`).

- [ ] **Step 6: Commit**

```bash
git add README.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "docs: one server for every workspace — the Workspaces page, sign-in per server, --workspace, and what viewers see

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```
