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
from codetortoise.paths import canon, within
from codetortoise.pipeline import AiPool, JobRunner
from codetortoise.services import Services, build_services, make_llm, make_strong, strip_flags_key
from codetortoise.sinks import MARKS_KEY, marks_key
from codetortoise.store import Store
from codetortoise.vcs.p4runner import P4Runner

LOCAL = "local"            # the Perforce server of a workspace with no p4port (§5)
LOADING = "loading"        # a workspace's reason while its bundle builds
STOP_WAIT = 600.0          # seconds a new bundle waits for the stopped queue it replaces to end
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

    @property
    def scope(self) -> str:
        """The scope keying its store entries: its bundle's (one built on its own keeps the store's own keys), else its
        id's, so its marks answer while it has no bundle (final review M5)."""
        return self.svc.scope if self.svc is not None else scope_of(self.id)


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
        self._guards: dict[int, threading.Lock] = {}       # by workspace id: see guard()
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
        was, now = server_of(row["p4port"] if row else ws.p4port), server_of(ws.p4port)
        if was != now and (n := self.store.review_count(wid)):     # the host's to decide; said (final review M4)
            log.warning("the workspace in tortoise.yaml moved from the Perforce server %s to %s: its %d review(s) now "
                        "show to those signed in there", was, now, n)
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
        overlap = None if seed else self._overlap(row["root"])
        if overlap and reason == LOADING:
            reason = f"its root {overlap}: change its root or the toolchain folders"
        ws = Workspace(id=row["id"], name=row["name"], server=server_of(row["p4port"]), owner=row["p4user"],
                       seed=seed, cfg=cfg, reason=reason)
        if reason != LOADING:
            ws.loaded.set()                              # nothing to build until its owner edits it
        return ws

    def _start(self, ws: Workspace, after: JobRunner | None = None, reindex: bool = False) -> None:
        """Build its bundle in the background: a slow Perforce server or a deep glob holds no request, and its row
        shows it loading until its checks have run (final review M11)."""
        if ws.reason == LOADING:
            self.spawn(lambda: self._build(ws, after, reindex))

    def settle(self, ws: Workspace, timeout: float = 120.0) -> None:
        """Wait while a workspace's bundle is still being built (right after startup), so a request then is answered
        once it has loaded rather than refused."""
        if ws.reason == LOADING:
            ws.loaded.wait(timeout)

    def _build(self, ws: Workspace, after: JobRunner | None = None, reindex: bool = False) -> None:
        try:
            self._load(ws, after, reindex)
        finally:
            ws.loaded.set()

    def _load(self, ws: Workspace, after: JobRunner | None = None, reindex: bool = False) -> None:
        """Build a workspace's bundle and start its queue; a failure keeps the workspace, not ready, with the reason
        (§11). Its symbol index is built when the bundle first loads, or with `reindex` (§6). `after`: the stopped queue
        of the bundle it replaces, whose index build ends before this one's starts."""
        svc = runner = None
        try:
            svc = build_services(ws.cfg, self.llm, strong=self.strong, store=self.store, ledger=self.ledger,
                                 home=self.home(ws.id), scope=scope_of(ws.id), folders=self.folders(ws),
                                 outside=self.outside())
            runner = self.runner_class(svc, self.pool)
        except Exception as e:  # a missing root, an unreadable compile database: shown, never fatal
            ws.reason = f"could not load: {type(e).__name__}: {e}"
            log.warning("workspace %s: %s", ws.name, ws.reason)
        if runner is not None and after is not None and not after.join(STOP_WAIT):
            log.warning("workspace %s: the queue it replaces still runs after %.0f s", ws.name, STOP_WAIT)
        with self._lock:
            kept = self._ws.get(ws.id) is ws             # not removed or replaced while it was building
            if kept and runner is not None:
                svc.owner_ticket = self._tickets.get((ws.server, ws.owner))
                runner.start()
                ws.runner, ws.svc = runner, svc
        if not kept:
            if svc is not None:
                svc.index.close()
            if self.store.get_workspace(ws.id) is None:  # removed: the folder its build made goes too (final review M2)
                shutil.rmtree(self.home(ws.id), ignore_errors=True)
            return
        if runner is None:
            return
        if reindex or svc.index.generation() == 0:
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
        with self.guard(ws.id):                          # two at once try it once (final review M2)
            ws = self.get(ws.id) or ws
            again = ws.svc is None and ws.reason is not None and ws.reason.startswith("could not load")
            if again:
                ws.reason = LOADING
                ws.loaded.clear()
        if again:
            self._build(ws)
        else:
            self.settle(ws)                              # another's try may be under way
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

    def guard(self, wid: int) -> threading.Lock:
        """What a change of workspace `wid` holds from its checks to its effect — an edit, a remove, a review queued in
        it, a bundle tried again — so that none acts on what another has just changed (final review M2)."""
        with self._lock:
            return self._guards.setdefault(wid, threading.Lock())

    def folders(self, ws: Workspace) -> list[str] | None:
        """The only folders a workspace's toolchain runs compilers and loads libclang from: tortoise.yaml's
        server.toolchain_folders for one added in the UI; None (as configured) for tortoise.yaml's own (final review
        I3)."""
        return None if ws.seed else self.base.server.toolchain_folders

    def outside(self) -> list[str]:
        """Folders that never count as toolchain folders: tortoise.yaml's workspace's, whose files are synced from its
        depot (a workspace added in the UI can't overlap a toolchain folder at all)."""
        return [str(self.base.workspace.root)] if self.base.workspace is not None else []

    def _overlap(self, root: str) -> str | None:
        """How `root` and a toolchain folder overlap, if they do: a workspace added in the UI there would make its synced
        files toolchains that such workspaces run (final review I3)."""
        real = os.path.realpath(root)
        for f in self.base.server.toolchain_folders:
            t = os.path.realpath(f)
            if within(real, t) or within(t, real):
                return (f"{root} and the toolchain folder {f} overlap; toolchain folders (server.toolchain_folders in "
                        "tortoise.yaml) hold only programs the host installs")
        return None

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
        P4CONFIG settings (P4CHARSET, P4TRUST) apply; None when it has none (a git workspace's server, §5). A workspace
        saved with a root that isn't there (§11) never stops sign-in to its server: a ready one is taken first, then any
        whose root is a folder, else p4 runs from no folder of ours."""
        p4 = [w for w in self.all() if w.server == server and w.cfg.workspace.vcs == "p4"]
        if not p4:
            return None
        there = [w for w in p4 if os.path.isdir(w.cfg.workspace.root)]
        ws = next((w for w in there if w.ready), there[0] if there else None)
        return P4Runner(server, None, (ws or p4[0]).cfg.workspace.p4_bin, cwd=ws.cfg.workspace.root if ws else None)

    # ---- adding, editing, removing (§8, §11) --------------------------------------------
    def add(self, fields: dict, by: str) -> Workspace:
        """Store a new workspace and start building its bundle; it is saved even when its checks fail."""
        self._validate(fields, None)
        try:
            wid = self.store.add_workspace(fields, "ui", by)
        except sqlite3.IntegrityError as e:                  # added by someone else meanwhile
            raise Conflict(self._taken(fields["name"], fields["root"], None) or str(e)) from e
        ws = self._record(self.store.get_workspace(wid))
        with self._lock:
            self._ws[wid] = ws
        self._start(ws)
        return ws

    def edit(self, wid: int, fields: dict, check: Callable[[dict], None] | None = None) -> Workspace:
        """Store its new fields and swap in a new bundle, built in the background; refused while a review waits or
        runs in its queue (§6), while an index build there is stopped (final review M3). `check` vets the change
        against its row as stored once no other change of it runs (final review I3-M7)."""
        with self.guard(wid):
            old = self._editable(wid)
            if check is not None:
                check(self.store.get_workspace(wid))
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
                old.runner.stop()                            # its index build ends early (final review M3)
            # a new root or compile database: the index catches up once the old queue's build has ended
            self._start(ws, after=old.runner, reindex=True)
        return ws

    def remove(self, wid: int) -> None:
        """Forget a workspace with no reviews: its row, its folder and its store entries."""
        with self.guard(wid):
            ws = self._editable(wid)
            n = self.store.review_count(wid)
            if n:
                raise Conflict(f"the workspace {ws.name} has {n} review(s); a workspace with reviews is kept")
            self._idle(ws)
            with self._lock:
                self._ws.pop(wid, None)
            if ws.runner is not None:
                ws.runner.stop()                             # its index build ends early (final review M3)
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
        overlap = self._overlap(fields["root"])
        if overlap:
            raise Invalid(f"root: {overlap}")
        if not fields.get("p4user"):
            raise Invalid("user: the Perforce user its reads run as")
        if fields["vcs"] == "p4" and not (fields.get("p4port") and fields.get("client")):
            raise Invalid("a Perforce workspace needs its server (P4PORT) and its client")
        # a git workspace is a dev-mode fixture (§5): in p4 mode it would serve any file under its root to whoever
        # signs in to the server it is labelled with
        if fields["vcs"] == "git" and self.base.auth.mode != "dev":
            raise Invalid("version control: a git workspace is for dev mode only (auth.mode: dev)")
        clash = self._taken(fields["name"], fields["root"], wid)
        if clash:
            raise Conflict(clash)
        try:
            return effective_config(self.base, fields)
        except ConfigError as e:
            raise Invalid(str(e)) from e

    # ---- command-line tools (§10) -------------------------------------------------------
    def tool_workspace(self, name: str | None = None, review: int | None = None) -> Workspace:
        """The workspace a command-line tool works on: the one named, else the `review`'s (final review M7), else the
        seed, else the only one; its bundle built here, without a queue."""
        if self.base.workspace is not None:
            self._register_seed()
        rows = {r["name"]: r for r in self.store.list_workspaces()}
        got = self.store.get_review(review) if name is None and review is not None else None
        if got is not None and got.get("workspace_id") is not None:
            name = next((n for n, r in rows.items() if r["id"] == got["workspace_id"]), None)
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
                                home=self.home(ws.id), scope=scope_of(ws.id), folders=self.folders(ws),
                                outside=self.outside())
        ws.reason = None
        return ws
