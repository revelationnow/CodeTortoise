"""Wires configuration into long-lived services shared by the pipeline and the web app."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from codetortoise.config import Config
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import LayerModel, infer_layers
from codetortoise.llm.client import LlmClient, LlmError
from codetortoise.llm.storyboard import name_layers
from codetortoise.store import Store
from codetortoise.swarm import SwarmClient
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.vcs.gitfixture import GitFixtureSource
from codetortoise.vcs.p4runner import P4Runner
from codetortoise.vcs.p4source import P4Source
from codetortoise.vcs.source import Source


class LayersProvider:
    """Layer model cached per symbol-index generation (in memory and in the store)."""

    def __init__(self, cfg: Config, index: SymbolIndex, store: Store, llm: LlmClient | None):
        self.cfg, self.index, self.store, self.llm = cfg, index, store, llm
        self._lock = threading.Lock()
        self._model: LayerModel | None = None

    def _key(self) -> str:
        return f"layers:{self.cfg.workspace.root}:{self.index.generation()}"

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
                        model = name_layers(model, self.llm)
                    except LlmError:
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
    swarm_override: Callable[[], SwarmClient | None] | None = field(default=None, repr=False)

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
    return LlmClient(cfg.llm.base_url, key, cfg.llm.model, timeout=cfg.llm.timeout_s)


def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | None = None) -> Services:
    data = cfg.server.data_dir
    data.mkdir(parents=True, exist_ok=True)
    store = Store(data / "tortoise.db")
    index = SymbolIndex(data / "symbols.db")
    cdb = CompileDb.load(cfg.workspace.compile_commands) if cfg.workspace.compile_commands.exists() else CompileDb([])
    tc = Toolchain(cfg.toolchain, cdb, data / "toolchain")
    llm = llm if llm is not None else make_llm(cfg)
    p4 = None
    if source is None:
        if cfg.workspace.vcs == "git":
            source = GitFixtureSource(cfg.workspace.root)
        else:
            p4 = P4Runner(cfg.workspace.p4port or "", cfg.workspace.client, cfg.workspace.p4_bin)
            source = P4Source(p4)
    return Services(cfg=cfg, store=store, source=source, index=index, cdb=cdb, toolchain=tc, llm=llm,
                    layers=LayersProvider(cfg, index, store, llm), p4=p4)
