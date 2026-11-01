"""tortoise.yaml configuration."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    public_url: str = "http://127.0.0.1:8765"
    data_dir: Path = Path(".tortoise")
    tls_cert: Path | None = None     # both set: serve HTTPS (spec §14.2)
    tls_key: Path | None = None
    # the only folders a workspace added in the UI runs compilers and loads libclang from (final review I3 of spec
    # 2026-10-31); the workspace described here is not held to them
    toolchain_folders: list[str] = Field(default_factory=lambda: ["/usr", "/opt"])


class WorkspaceConfig(BaseModel):
    name: str | None = None          # what the UI calls it (spec 2026-10-31 §4); default: its client's, or its root folder's
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
    target: str | None = None        # e.g. "dsp"
    libclang: str | None = None
    # more -isystem folders for matching files (relative to the workspace root), after the compiler's own
    system_include_dirs: list[str] = Field(default_factory=list)


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


class TargetRule(BaseModel):
    match: str                       # glob on the workspace-relative path, e.g. "modem/**"
    name: str                        # the target's name on stories (spec 2026-10-05-two-tier-stories §3.1)


class SwarmConfig(BaseModel):
    url: str | None = None


class LlmBudget(BaseModel):
    per_review: int = 200          # AI calls per review: everyone and the pipeline together
    per_person_daily: int = 100    # AI calls one person can trigger per day (UTC), across reviews
    per_mention: int = 10          # rounds one @tortoise answer may take (one AI call however many); the owner sets it per review
    tier1_per_review: int = 40     # strong-model calls per review: stories, merge and risk passes (spec 2026-10-05 §9)


class StrongLlmConfig(BaseModel):
    """The strong model that forms stories and reviews their risks (spec 2026-10-05-two-tier-stories §9)."""
    base_url: str                  # the endpoint, e.g. https://api.openai.com/v1 or https://api.anthropic.com/v1
    model: str
    api: Literal["chat", "responses", "messages"] = "chat"   # chat completions, OpenAI Responses or Anthropic Messages
    max_output_tokens: int | None = None   # the reply's token limit (Messages needs one: 8192 when unset)
    key_env: str = "TORTOISE_STRONG_KEY"
    context_tokens: int = 64000
    temperature: float | None = 0  # None for endpoints that reject it
    rounds: int = 20               # reads one stories or review call may make (one AI call however many)
    agree: Literal[1, 2] = 1       # 2: two runs (a third breaks ties) for stable stories
    timeout_s: float = 300.0


class LlmConfig(BaseModel):
    base_url: str | None = None
    api_key_env: str = "TORTOISE_LLM_KEY"
    model: str = "gpt-4o-mini"
    api: Literal["chat", "responses", "messages"] = "chat"   # chat completions, OpenAI Responses or Anthropic Messages
    max_output_tokens: int | None = None   # the reply's token limit (Messages needs one: 8192 when unset)
    max_output_tokens_cap: int = 32768   # no try asks either model for more output tokens than this
    request_log: Literal["all", "failed", "off"] = "all"   # HTTP requests kept: every one, a failed call's, or none
    request_log_days: int = 14     # logged requests older than this are deleted
    max_context_tokens: int = 64000
    timeout_s: float = 120.0
    concurrency: int = 4           # parallel LLM calls (finding explanations, chapter and flow narratives)
    upfront_flows: int = 3         # flow narratives written when a review runs (the rest on demand)
    upfront_stories: int = 3       # behaviour stories whose title and summary the AI writes when a review runs
    upfront_findings: int = 5      # high-severity findings the AI explains when a review runs, not on first open
    upfront_side_effects: int = 36  # side effects (new field writes) the AI judges when a review runs, 12 to a call
    budget: LlmBudget = Field(default_factory=LlmBudget)
    strong: StrongLlmConfig | None = None   # absent: the rules form the stories


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
    max_flows: int = 12            # accepted and ignored: a board's node budget bounds its flows
    board_max_nodes: int = 30      # nodes a board draws before the reader expands it; larger changes are split
    board_blast_nodes: int = 60    # accepted and ignored (neighbours fill a board's budget)
    cluster_min_changed: int = 3   # clusters with fewer changed functions merge with one in the same directory
    overview_max_clusters: int = 60  # more clusters than this: the smallest merge further
    max_stories: int = 15          # entries on a review's story list (spec 2026-10-04 §2.4)
    story_graph_nodes: int = 12    # nodes a story's graph shows before the reader expands it
    entrypoint_patterns: list[str] = Field(
        default_factory=lambda: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"])
    sink_threshold: int = 20       # a field more unchanged functions than this touch is a shared sink; 0 = off
    sink_fields: list[str] = Field(default_factory=list)   # fnmatch patterns on record::field: always shared sinks


class Config(BaseModel):
    owner: str = ""                  # the seed workspace's owner; defaults to P4USER (P4CONFIG file, then environment)
    server: ServerConfig = Field(default_factory=ServerConfig)
    workspace: WorkspaceConfig | None = None   # the seed workspace (spec 2026-10-31 §4); none: the stored ones alone
    toolchain: ToolchainConfig = Field(default_factory=ToolchainConfig)
    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    targets: list[TargetRule] = Field(default_factory=list)   # first match names a file's build target


class ConfigError(ValueError):
    pass


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
    srv.toolchain_folders = [f if Path(f).is_absolute() else str((base / f).resolve()) for f in srv.toolchain_folders]
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
    """A workspace's Advanced settings: tortoise.yaml's `toolchain`, `targets` and `analysis` keys, as YAML text. No
    anchors or aliases: an alias repeats what it names without copying it, so a kilobyte of them unfolds into gigabytes
    wherever the settings are copied out (final review I3 of spec 2026-10-31)."""
    try:
        if any(isinstance(t, (yaml.AnchorToken, yaml.AliasToken)) for t in yaml.scan(text or "")):
            raise ConfigError("settings: YAML anchors and aliases (& and *) aren't allowed here")
        got = yaml.safe_load(text or "") or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"settings: not YAML: {e}") from e
    if not isinstance(got, dict):
        raise ConfigError("settings: a mapping of toolchain, targets and analysis")
    extra = sorted(str(k) for k in got if k not in SETTINGS_KEYS)
    if extra:
        raise ConfigError(f"settings: only toolchain, targets and analysis belong here, not {', '.join(extra)}")
    return got


PROGRAM_KEYS = ("clang", "libclang", "search_paths", "query_compilers")   # toolchain keys naming what the server runs


def program_settings(text: str | None) -> tuple:
    """What a workspace's settings name for the server to run or load (final review I3 of spec 2026-10-31): the
    toolchain's clang, libclang, search_paths and query_compilers, and each override's clang and libclang, in a form two
    settings compare by. A default or empty value names nothing; settings that don't parse name nothing here (saving
    them says why)."""
    try:
        got = parse_settings(text)
    except ConfigError:
        return ()
    tc = got.get("toolchain")
    if not isinstance(tc, dict):
        return ()
    named = tuple((k, json.dumps(tc[k], sort_keys=True, default=str)) for k in PROGRAM_KEYS
                  if tc.get(k) not in (None, "", []) and not (k == "query_compilers" and tc[k] == "outside_workspace"))
    overrides = tc.get("overrides") if isinstance(tc.get("overrides"), list) else []
    return named + tuple(sorted(json.dumps({k: o.get(k) for k in ("match", "clang", "libclang")}, sort_keys=True,
                                           default=str)
                                for o in overrides if isinstance(o, dict) and (o.get("clang") or o.get("libclang"))))


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
