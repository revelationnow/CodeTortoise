"""tortoise.yaml configuration."""
from __future__ import annotations

from collections.abc import Mapping
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
    compile_commands: Literal["auto"] | Path | list[Path]   # a path, a list of paths/globs, or every one under build_root
    build_root: Path | None = None
    p4_bin: str = "p4"
    p4_sources: dict[str, str] = Field(default_factory=dict)   # where p4port, client and owner came from (set on load)


class ToolchainOverride(BaseModel):
    match: str                       # glob on the workspace-relative source path, e.g. "dsp/**"
    compile_commands: Path | None = None   # use this database's entry for matching files
    clang: str | None = None         # compiler to query for built-in includes and macros
    target: str | None = None        # e.g. "hexagon"
    libclang: str | None = None


class ToolchainConfig(BaseModel):
    clang: str | None = None         # query this compiler for every file (default: each entry's own compiler)
    target: str | None = None        # target for files whose command names none (default: from the compiler)
    overrides: list[ToolchainOverride] = Field(default_factory=list)
    libclang: str | None = None
    search_paths: list[str] = Field(default_factory=list)   # folders to search for a newer libclang
    # run compilers named in compile databases to learn their includes and macros: not those inside the workspace
    # (a database or toolchain synced from the depot) unless "all"; "off" never runs them
    query_compilers: Literal["outside_workspace", "all", "off"] = "outside_workspace"
    resource_dir: str | None = None
    strip_flags: list[str] = Field(default_factory=list)


class SwarmConfig(BaseModel):
    url: str | None = None


class LlmBudget(BaseModel):
    per_review: int = 200          # AI calls per review: everyone and the pipeline together
    per_person_daily: int = 100    # AI calls one person can trigger per day (UTC), across reviews
    per_mention: int = 6           # rounds one @tortoise answer may take


class LlmConfig(BaseModel):
    base_url: str | None = None
    api_key_env: str = "TORTOISE_LLM_KEY"
    model: str = "gpt-4o-mini"
    max_context_tokens: int = 64000
    timeout_s: float = 120.0
    concurrency: int = 4           # parallel LLM calls (finding explanations, chapter and flow narratives)
    upfront_flows: int = 3         # flow narratives written when a review runs (the rest on demand)
    budget: LlmBudget = Field(default_factory=LlmBudget)


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
    index_scope: Literal["compile_db", "workspace"] = "compile_db"   # files the symbol index parses
    heuristic_fanin_cap: int = 50  # names with more out-of-TU callers/refs than this are not expanded heuristically
    max_flows: int = 12            # review board: flows listed (entry -> change -> where the effect lands)
    board_max_nodes: int = 150     # review board: functions/fields drawn
    board_blast_nodes: int = 60    # review board: top blast-radius functions included
    entrypoint_patterns: list[str] = Field(
        default_factory=lambda: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"])


class Config(BaseModel):
    owner: str = ""                  # defaults to P4USER (P4CONFIG file, then environment)
    server: ServerConfig = Field(default_factory=ServerConfig)
    workspace: WorkspaceConfig
    toolchain: ToolchainConfig = Field(default_factory=ToolchainConfig)
    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)


class ConfigError(ValueError):
    pass


def load_config(path: Path, env: Mapping[str, str] | None = None) -> Config:
    """Read tortoise.yaml. Missing `owner`, `workspace.p4port` and `workspace.client` come from Perforce's own settings:
    the P4CONFIG file found from the workspace root, then P4USER/P4PORT/P4CLIENT in the environment (`env`)."""
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
