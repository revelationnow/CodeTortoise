"""Wires configuration into long-lived services shared by the pipeline and the web app."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from codetortoise import layers as layers_mod
from codetortoise.config import Config
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import LayerModel, infer_layers
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger
from codetortoise.llm.storyboard import name_layers
from codetortoise.store import Store
from codetortoise.swarm import SwarmClient
from codetortoise.toolchain.compile_db import CompileDb, include_dirs, load_databases
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.vcs.gitfixture import GitFixtureSource
from codetortoise.vcs.p4runner import P4Runner
from codetortoise.vcs.p4source import P4Source
from codetortoise.vcs.source import Source


class LayersProvider:
    """Layer model cached per symbol-index generation (in memory and in the store)."""

    def __init__(self, cfg: Config, index: SymbolIndex, store: Store, llm: LlmClient | None,
                 ledger: Ledger | None = None):
        self.cfg, self.index, self.store, self.llm, self.ledger = cfg, index, store, llm, ledger
        self._lock = threading.Lock()
        self._model: LayerModel | None = None

    def _key(self) -> str:
        return f"layers:v{layers_mod.ALGORITHM_VERSION}:{self.cfg.workspace.root}:{self.index.generation()}"

    def get(self) -> LayerModel | None:
        with self._lock:
            if self.index.generation() == 0:
                return None
            if self._model is not None and self._model.generation == self.index.generation():
                return self._model
            cached = self.store.kv_get(self._key())
            if cached:
                self._model = LayerModel.model_validate(cached)
            else:
                a = self.cfg.analysis
                model = infer_layers(self.index, str(self.cfg.workspace.root), a.module_min_files, a.max_layers)
                if self.llm is not None:
                    try:
                        model = (self.ledger.call(self.llm, None, None, "layers", f"generation {self.index.generation()}",
                                                  lambda llm: name_layers(model, llm))
                                 if self.ledger else name_layers(model, self.llm))
                    except Exception:  # naming is cosmetic; keep the inferred L<n> names
                        pass
                self.store.kv_put(self._key(), model)
                self._model = model
            overrides = self.store.kv_get("layer_overrides") or {}
            for layer in self._model.layers:
                if str(layer.level) in overrides:
                    layer.name = overrides[str(layer.level)]
            return self._model


@dataclass
class Services:
    cfg: Config
    store: Store
    source: Source
    index: SymbolIndex
    cdb: CompileDb
    toolchain: Toolchain
    llm: LlmClient | None
    layers: LayersProvider
    p4: P4Runner | None = None
    owner_ticket: str | None = None
    ledger: Ledger | None = None                  # every AI call goes through it (spec 2026-10-03 §2)
    strong: LlmClient | None = None               # tier 1: forms stories and reviews their risks (spec 2026-10-05)
    swarm_override: Callable[[], SwarmClient | None] | None = field(default=None, repr=False)

    def build_index(self, full: bool = False) -> int:
        """Bring the symbol index up to date (incremental unless `full`), resolving #includes with the compile DB's
        include dirs. Scope: the compile DB's files and the headers they include, or the whole workspace
        (`analysis.index_scope`, or when the compile DB is empty)."""
        seeds = self.cdb.files() if self.cfg.analysis.index_scope == "compile_db" and self.cdb.entries else None
        return self.index.build(self.cfg.workspace.root, workers=self.cfg.analysis.workers,
                                include_dirs=include_dirs(self.cdb), seeds=seeds, full=full)

    def remember_stripped(self, flags: list[str]) -> None:
        """Flags libclang rejected: skipped for all later parses of this workspace (persisted)."""
        self.toolchain.strip.update(flags)
        self.store.kv_put(f"strip_flags:{self.cfg.workspace.root}", sorted(self.toolchain.strip))

    def swarm(self) -> SwarmClient | None:
        if self.swarm_override is not None:
            return self.swarm_override()
        if not self.cfg.swarm.url or self.owner_ticket is None:
            return None
        return SwarmClient(self.cfg.swarm.url, self.cfg.owner, self.owner_ticket)


def make_llm(cfg: Config) -> LlmClient | None:
    key = os.environ.get(cfg.llm.api_key_env, "")
    if not cfg.llm.base_url:
        return None
    return LlmClient(cfg.llm.base_url, key, cfg.llm.model, timeout=cfg.llm.timeout_s, api=cfg.llm.api,
                     max_output_tokens=cfg.llm.max_output_tokens,
                     cap=cfg.llm.max_output_tokens_cap)


def make_strong(cfg: Config) -> LlmClient | None:
    s = cfg.llm.strong
    if s is None:
        return None
    return LlmClient(s.base_url, os.environ.get(s.key_env, ""), s.model, timeout=s.timeout_s, temperature=s.temperature,
                     api=s.api, max_output_tokens=s.max_output_tokens, cap=cfg.llm.max_output_tokens_cap)


def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | None = None,
                   strong: LlmClient | None = None) -> Services:
    data = cfg.server.data_dir
    data.mkdir(parents=True, exist_ok=True)
    store = Store(data / "tortoise.db")
    index = SymbolIndex(data / "symbols.db")
    cdb = load_databases(cfg.workspace.compile_commands, cfg.workspace.root, cfg.workspace.build_root)
    tc = Toolchain(cfg.toolchain, cdb, data / "toolchain", root=cfg.workspace.root)
    tc.strip.update(store.kv_get(f"strip_flags:{cfg.workspace.root}") or [])
    llm = llm if llm is not None else make_llm(cfg)
    p4 = None
    if source is None:
        if cfg.workspace.vcs == "git":
            source = GitFixtureSource(cfg.workspace.root)
        else:
            p4 = P4Runner(cfg.workspace.p4port or "", cfg.workspace.client, cfg.workspace.p4_bin, cwd=cfg.workspace.root)
            source = P4Source(p4)
    ledger = Ledger(store, cfg.llm.budget)
    return Services(cfg=cfg, store=store, source=source, index=index, cdb=cdb, toolchain=tc, llm=llm,
                    layers=LayersProvider(cfg, index, store, llm, ledger), p4=p4, ledger=ledger,
                    strong=strong if strong is not None else make_strong(cfg))
