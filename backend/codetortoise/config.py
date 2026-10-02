"""tortoise.yaml configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    public_url: str = "http://127.0.0.1:8765"
    data_dir: Path = Path(".tortoise")
    tls_cert: Path | None = None     # both set: serve HTTPS (spec §14.2)
    tls_key: Path | None = None


class WorkspaceConfig(BaseModel):
    vcs: Literal["p4", "git"] = "p4"
    p4port: str | None = None
    client: str | None = None
    root: Path
    compile_commands: Path
    p4_bin: str = "p4"


class ToolchainConfig(BaseModel):
    clang: str | None = None
    libclang: str | None = None
    resource_dir: str | None = None
    strip_flags: list[str] = Field(default_factory=list)


class SwarmConfig(BaseModel):
    url: str | None = None


class LlmConfig(BaseModel):
    base_url: str | None = None
    api_key_env: str = "TORTOISE_LLM_KEY"
    model: str = "gpt-4o-mini"
    max_context_tokens: int = 64000
    timeout_s: float = 120.0
    concurrency: int = 4           # parallel LLM calls (finding explanations, chapter and flow narratives)
    max_flow_narratives: int = 6   # review board flows whose description the LLM rewrites


class AuthConfig(BaseModel):
    mode: Literal["p4", "dev"] = "p4"


class AnalysisConfig(BaseModel):
    caller_hops: int = 2
    tu_budget: int = 200
    flow_depth: int = 4
    blast_hops: int = 4
    header_sample_tus: int = 20
    module_min_files: int = 5
    max_layers: int = 8
    workers: int = 4
    heuristic_fanin_cap: int = 50  # names with more out-of-TU callers/refs than this are not expanded heuristically
    max_flows: int = 12            # review board: flows listed (entry -> change -> where the effect lands)
    board_max_nodes: int = 150     # review board: functions/fields drawn
    board_blast_nodes: int = 60    # review board: top blast-radius functions included
    entrypoint_patterns: list[str] = Field(
        default_factory=lambda: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"])


class Config(BaseModel):
    owner: str
    server: ServerConfig = Field(default_factory=ServerConfig)
    workspace: WorkspaceConfig
    toolchain: ToolchainConfig = Field(default_factory=ToolchainConfig)
    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> Config:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
    try:
        cfg = Config.model_validate(raw)
    except Exception as e:  # pydantic.ValidationError
        raise ConfigError(str(e)) from e
    if cfg.workspace.vcs == "p4" and (not cfg.workspace.p4port or not cfg.workspace.client):
        raise ConfigError("workspace.p4port and workspace.client are required when workspace.vcs is p4")
    base = path.parent
    ws = cfg.workspace
    ws.root = (base / ws.root).resolve() if not ws.root.is_absolute() else ws.root
    ws.compile_commands = (base / ws.compile_commands).resolve() if not ws.compile_commands.is_absolute() else ws.compile_commands
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
