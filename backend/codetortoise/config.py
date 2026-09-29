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
    return cfg
