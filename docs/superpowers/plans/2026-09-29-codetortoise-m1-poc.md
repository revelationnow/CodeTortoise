# CodeTortoise M1 (Proof of Concept) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally hosted web app that turns one or more Perforce changelists into a layered review storyboard for C/C++ code. It covers call-flow diffs, blast radius over call and field-data coupling (including writes through local aliases), contract, field-mutation and header fan-out findings, and grounded LLM narrative. Viewers sign in with P4 credentials and comment, and P4 Swarm is used as a side channel.

**Architecture:** A single Python process (FastAPI, a background job runner and SQLite) serves a React single-page app. A staged pipeline turns CLs into results: ingest (p4 or a git fixture), then tree-sitter diffmap, then budgeted TU selection over a repo-wide tree-sitter symbol index, then libclang facts for the before and after variants (vendor libclang or the bundled one, with implicit flags queried from the driver), then the impact graph, then detectors, then the storyboard (deterministic skeleton plus an optional OpenAI-compatible LLM pass with citation grounding). Every stage records its status, and failures degrade the review instead of aborting it.

**Tech Stack:** Python ≥3.12 with uv, FastAPI, uvicorn, pydantic v2, httpx, networkx, `libclang` (PyPI wheel 18.1.1 bindings), `tree-sitter` with `tree-sitter-c`/`tree-sitter-cpp`, SQLite, pytest and ruff. On the frontend: React 19, TypeScript 5.9, Vite 8, react-router 7, cytoscape with cytoscape-elk, jsdiff, vitest and Playwright.

**Spec:** `docs/superpowers/specs/2026-09-29-codetortoise-design.md` (section 14 records decisions made while planning; it overrides earlier sections where they differ).

**Provenance:** every code block in this plan was run before the plan was written. The tasks were replayed in order in a fresh tree: each task's tests failed before its implementation and passed after it, the whole suite and ruff stayed green after every backend task, the frontend built after each frontend task, and the Playwright smoke passed at the end. The expected outputs below come from that replay.

## Global Constraints

- **Paths:** all paths are relative to the repository root. Backend commands run in `backend/` and frontend commands in `frontend/`.
- **Python:** `requires-python = ">=3.12"`. Dependencies are declared once, in Task 1's `backend/pyproject.toml`; do not add new ones without a reason recorded in the commit.
- **C/C++ first:** C and C++ are the first-class languages. Python, Rust and JS are out of scope for M1.
- **Base workspace is read-only:** it is never synced, unshelved or edited. All Perforce access goes through `P4Runner`, which allowlists `describe, print, where, have, client, info, changes, fstat, files` plus `login -p`.
- **Credentials:** passwords go only to `p4 login -p` on stdin and are never stored or logged. Non-owner tickets are discarded. The owner's ticket is held in memory only, for Swarm.
- **LLM API key:** read from the environment variable named by `llm.api_key_env` (default `TORTOISE_LLM_KEY`). It is never persisted or logged and appears only in the `Authorization` header.
- **Sessions:** random 256-bit token (`secrets.token_urlsafe(32)`), stored as a SHA-256 hash, 7-day expiry, HTTP-only `SameSite=Lax` cookie `ct_session`.
- **Analysis defaults:** `caller_hops: 2`, `tu_budget: 200`, `flow_depth: 4`, `blast_hops: 4`, `header_sample_tus: 20`, `module_min_files: 5`, `max_layers: 8`, `workers: 4`, `entrypoint_patterns: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"]`.
- **Blast radius:** edge weights are precise 1.0, may 0.6, heuristic 0.4. Score = Σ weight/hop, ×1.5 cross-layer caller, ×1.5 entry point, ×1.3 via virtual dispatch.
- **LLM:** 2 retries with backoff on transport errors, 5xx and 429, and one JSON repair round. Hypotheses and cross-layer effects without a valid citation (`N…` node id or `F…` finding id) are dropped. A narrative with no valid citation is badged "unverified".
- **Swarm:** never blocks a review. Summary posts are idempotent unless the owner confirms a repeat.
- **Style:** code style is enforced by ruff (`E, F, I, B, UP`, line length 132).
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

These are the inputs the spec implies but does not spell out that are most likely to bite a real user, in order of likelihood. Each is pinned by a test in the task that owns the code.

1. **Symlinked or relative workspace roots:** the P4 client root, `compile_commands.json` and the symbol index disagree on path spelling. Analysis must still select the right TUs. Pinned by `test_symlinked_workspace_root_still_matches_compile_db` (Task 9) and by `canon()` being used by every path producer (Tasks 1, 3, 4, 6, 7, 10).
2. **Vendor compiler flags libclang does not know:** the parse must still be precise, not fail. Pinned by `test_unknown_vendor_flags_are_stripped_and_retried` (Task 10). Genuinely broken parses degrade confidence (`test_parse_errors_degrade_confidence`) or fall back to tree-sitter (`test_falls_back_to_treesitter_when_clang_raises`).
3. **CL sets with no C/C++ changes, or a CL number that does not exist:** the review finishes with a clear stage message, and dependent stages are skipped rather than crashing. Pinned by `test_change_without_c_code_completes` and `test_ingest_failure_skips_dependent_stages` (Task 17).
4. **LLM endpoint down, rejecting `response_format`, or replying with prose or invalid JSON:** reviewers still get the deterministic storyboard and findings, and the llm stage is marked degraded. Pinned by Task 13's client tests and `test_llm_failure_keeps_deterministic_storyboard` (Task 14).
5. **Binary or non-UTF-8 content in changelists:** binaries are never fetched, and text is decoded with replacement characters while keeping line numbers. Pinned by `test_shelved_cl_reads_base_rev_and_shelf` (binary case, Task 4) and `test_non_ascii_and_replacement_chars_keep_line_numbers` (Task 2).

---

### Task 1: Backend scaffold, configuration, canonical paths

Creates the uv-managed Python package, the repo `.gitignore`, the `tortoise.yaml` model and loader,
and `canon()` — the single function every module uses to compare file paths (so symlinked workspace roots,
`..` segments and relative compile-DB entries agree). All runtime dependencies are declared here once.

**Files:**
- Create: `backend/pyproject.toml`
- Create: `.gitignore`
- Create: `backend/codetortoise/__init__.py`
- Create: `backend/codetortoise/config.py`
- Create: `backend/codetortoise/paths.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `codetortoise.config` — `Config`, `ServerConfig`, `WorkspaceConfig`, `ToolchainConfig`, `SwarmConfig`,
  `LlmConfig`, `AuthConfig`, `AnalysisConfig` (pydantic models, fields as in the code), `load_config(path: Path) -> Config`,
  `ConfigError(ValueError)`.
- Produces: `codetortoise.paths.canon(path: str) -> str` (realpath of abspath).

- [ ] **Step 1: Create project files**

`backend/pyproject.toml`:

```toml
[project]
name = "codetortoise"
version = "0.1.0"
description = "Deep, layered code review for C/C++ changelists (Perforce + Swarm side channel)"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "httpx>=0.27",
    "pydantic>=2.8",
    "pyyaml>=6.0",
    "networkx>=3.3",
    "libclang>=18.1.1",
    "tree-sitter>=0.25",
    "tree-sitter-c>=0.24",
    "tree-sitter-cpp>=0.23",
]

[project.scripts]
codetortoise = "codetortoise.cli:main"

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.6"]

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["codetortoise"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
filterwarnings = ["ignore::DeprecationWarning:fastapi.testclient", "ignore:Using `httpx`"]

[tool.ruff]
line-length = 132
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E741", "B008"]
```

`.gitignore`:

```gitignore
# Python
__pycache__/
*.pyc
backend/.venv/
backend/.pytest_cache/
.ruff_cache/
# runtime data
.tortoise/
# frontend
frontend/node_modules/
frontend/test-results/
frontend/playwright-report/
# built SPA (produced by `npm run build` in frontend/)
backend/codetortoise/web/static/
```

`backend/codetortoise/__init__.py`:

```python
__version__ = "0.1.0"
```

Then create the environment: `cd backend && uv sync` (creates `backend/.venv` with runtime and dev dependencies).

- [ ] **Step 2: Write the failing test**

`backend/tests/test_config.py`:

```python
import pytest

from codetortoise.config import ConfigError, load_config


def write(tmp_path, text):
    p = tmp_path / "tortoise.yaml"
    p.write_text(text)
    return p


def test_loads_and_resolves_relative_paths(tmp_path):
    cfg = load_config(write(tmp_path, """
owner: anoop
workspace:
  vcs: p4
  p4port: ssl:p4:1666
  client: anoop-ws
  root: ws
  compile_commands: ws/build/compile_commands.json
"""))
    assert cfg.owner == "anoop"
    assert cfg.workspace.root == (tmp_path / "ws").resolve()
    assert cfg.workspace.compile_commands == (tmp_path / "ws/build/compile_commands.json").resolve()
    assert cfg.server.data_dir == (tmp_path / ".tortoise").resolve()
    assert cfg.analysis.tu_budget == 200
    assert cfg.auth.mode == "p4"


def test_p4_requires_port_and_client(tmp_path):
    with pytest.raises(ConfigError, match="p4port"):
        load_config(write(tmp_path, "owner: a\nworkspace: {root: /w, compile_commands: /w/cc.json}\n"))


def test_git_workspace_needs_no_p4(tmp_path):
    cfg = load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"))
    assert cfg.workspace.vcs == "git"


def test_invalid_yaml_is_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, "owner: [unclosed\n"))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && uv sync && uv run pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.config'`

- [ ] **Step 4: Implement**

`backend/codetortoise/config.py`:

```python
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
```

`backend/codetortoise/paths.py`:

```python
"""Canonical file identity. Every module compares files through canon() so that symlinked
workspace roots, `..` segments and relative compile-DB entries all agree."""
from __future__ import annotations

import os


def canon(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_config.py -q`
Expected: `4 passed`

- [ ] **Step 6: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `4 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml .gitignore backend/codetortoise/__init__.py backend/tests/test_config.py backend/codetortoise/config.py backend/codetortoise/paths.py
git commit -m "feat(backend): scaffold package, config loader, canonical paths"
```

---

### Task 2: Tree-sitter C/C++ structural parser (`cparse`)

Flag-free, fast parsing used for (a) the repo-wide symbol index, (b) mapping diffs to functions, and
(c) the fallback extractor when clang cannot parse a TU. It returns function definitions with
namespace/class-qualified names (matching clang's qualified names), prototypes, types, macros, includes,
call sites (callee *name* only) and member references with a write flag.

**Files:**
- Create: `backend/codetortoise/cparse.py`
- Test: `backend/tests/test_cparse.py`

**Interfaces:**
- Produces: `parse_source(path: str, text: str) -> ParsedFile` with lists `functions: list[FuncDef]`,
  `decls: list[FuncDecl]`, `types: list[TypeDef]`, `macros: list[MacroDef]`, `calls: list[CallSite]`,
  `includes: list[str]`, `members: list[MemberRef]`.
- `FuncDef(qualname, name, start_line, end_line, signature, text_hash)`, `FuncDecl(qualname, line, text)`,
  `TypeDef(name, kind, start_line, end_line, text)`, `MacroDef(name, line, text)`, `CallSite(caller|None, callee, line)`,
  `MemberRef(fn|None, field, line, is_write)`. Lines are 1-based.
- Produces: `is_source(path) -> bool`, `is_header(path) -> bool`, `norm_ws(text) -> str`, `SOURCE_EXTS`, `HEADER_EXTS`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_cparse.py`:

```python
from codetortoise.cparse import is_header, is_source, parse_source

CPP = """
#include "cpp/engine.h"
#define LIMIT 4
namespace svc {
struct Local { int a; };
int Engine::step(State &st) {
  auto &r = st.inner;
  r.n += 2;
  helper(st.x);
  obj.method();
  return base(st) + 1;
}
int free_fn(int);
}
"""


def test_functions_get_namespace_qualified_names():
    pf = parse_source("e.cpp", CPP)
    assert [f.qualname for f in pf.functions] == ["svc::Engine::step"]
    f = pf.functions[0]
    assert f.name == "step"
    assert f.signature == "int Engine::step(State &st)"
    assert (f.start_line, f.end_line) == (6, 12)


def test_calls_members_includes_macros_types_decls():
    pf = parse_source("e.cpp", CPP)
    assert {c.callee for c in pf.calls} == {"helper", "method", "base"}
    assert all(c.caller == "svc::Engine::step" for c in pf.calls)
    members = {(m.field, m.is_write) for m in pf.members}
    assert ("n", True) in members and ("inner", False) in members and ("x", False) in members
    assert ("method", False) not in members  # callee member expressions are calls, not field refs
    assert pf.includes == ["cpp/engine.h"]
    assert [m.name for m in pf.macros] == ["LIMIT"]
    assert [t.name for t in pf.types] == ["svc::Local"]
    assert [d.qualname for d in pf.decls] == ["svc::free_fn"]


def test_function_hash_changes_with_body_only():
    a = parse_source("a.c", "int f(int x) { return x; }\n").functions[0]
    b = parse_source("a.c", "int f(int x) {   return x; }\n").functions[0]
    c = parse_source("a.c", "int f(int x) { return x + 1; }\n").functions[0]
    assert a.text_hash == b.text_hash != c.text_hash


def test_extension_helpers():
    assert is_source("a.c") and is_source("b.HPP") and not is_source("c.txt")
    assert is_header("x.h") and not is_header("x.cpp")


def test_non_ascii_and_replacement_chars_keep_line_numbers():
    text = "/* d\u00e9j\u00e0 vu \ufffd\ufffd */\nint f(void) { return 0; }\n"
    (f,) = parse_source("x.c", text).functions
    assert (f.qualname, f.start_line) == ("f", 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_cparse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.cparse'`

- [ ] **Step 3: Implement**

`backend/codetortoise/cparse.py`:

```python
"""Tree-sitter based C/C++ structural parsing (fast, flag-free, heuristic)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import PurePath

import tree_sitter as ts
import tree_sitter_c
import tree_sitter_cpp

C_EXTS = {".c"}
CPP_EXTS = {".cc", ".cpp", ".cxx", ".c++"}
HEADER_EXTS = {".h", ".hh", ".hpp", ".hxx", ".inl"}
SOURCE_EXTS = C_EXTS | CPP_EXTS | HEADER_EXTS

_LANG_C = ts.Language(tree_sitter_c.language())
_LANG_CPP = ts.Language(tree_sitter_cpp.language())


def is_source(path: str) -> bool:
    return PurePath(path).suffix.lower() in SOURCE_EXTS


def is_header(path: str) -> bool:
    return PurePath(path).suffix.lower() in HEADER_EXTS


def _parser_for(path: str) -> ts.Parser:
    lang = _LANG_C if PurePath(path).suffix.lower() in C_EXTS else _LANG_CPP
    return ts.Parser(lang)


def norm_ws(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class FuncDef:
    qualname: str
    name: str
    start_line: int
    end_line: int
    signature: str
    text_hash: str


@dataclass(frozen=True)
class TypeDef:
    name: str
    kind: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class MacroDef:
    name: str
    line: int
    text: str


@dataclass(frozen=True)
class CallSite:
    caller: str | None
    callee: str
    line: int


@dataclass(frozen=True)
class MemberRef:
    fn: str | None
    field: str
    line: int
    is_write: bool


@dataclass(frozen=True)
class FuncDecl:
    qualname: str
    line: int
    text: str


@dataclass
class ParsedFile:
    functions: list[FuncDef] = field(default_factory=list)
    decls: list[FuncDecl] = field(default_factory=list)
    types: list[TypeDef] = field(default_factory=list)
    macros: list[MacroDef] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    members: list[MemberRef] = field(default_factory=list)


def _txt(src: bytes, node: ts.Node | None) -> str:
    if node is None:
        return ""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_function_declarator(node: ts.Node | None) -> ts.Node | None:
    while node is not None:
        if node.type == "function_declarator":
            return node
        node = node.child_by_field_name("declarator")
    return None


def _callee_name(src: bytes, fn_node: ts.Node | None) -> str | None:
    if fn_node is None:
        return None
    t = fn_node.type
    if t == "identifier":
        return _txt(src, fn_node)
    if t == "field_expression":
        return _txt(src, fn_node.child_by_field_name("field")) or None
    if t == "qualified_identifier":
        return _txt(src, fn_node).replace(" ", "").split("::")[-1] or None
    if t == "template_function":
        return _callee_name(src, fn_node.child_by_field_name("name"))
    return None


def _is_write_target(node: ts.Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        return left is not None and left.id == node.id
    if parent.type == "update_expression":
        return True
    return False


def parse_source(path: str, text: str) -> ParsedFile:
    src = text.encode("utf-8", errors="replace")
    tree = _parser_for(path).parse(src)
    out = ParsedFile()
    stack: list[tuple[ts.Node, tuple[str, ...], str | None]] = [(tree.root_node, (), None)]
    while stack:
        node, scope, fn = stack.pop()
        t = node.type
        child_scope, child_fn = scope, fn
        if t == "namespace_definition":
            name = node.child_by_field_name("name")
            if name is not None:
                child_scope = scope + (_txt(src, name).replace(" ", ""),)
        elif t in ("class_specifier", "struct_specifier", "union_specifier", "enum_specifier"):
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if body is not None:
                nm = _txt(src, name_node).replace(" ", "")
                qual = "::".join(scope + (nm,)) if nm else ""
                out.types.append(TypeDef(qual, t.split("_")[0], node.start_point.row + 1,
                                         node.end_point.row + 1, norm_ws(_txt(src, node))))
                if nm and t != "enum_specifier":
                    child_scope = scope + (nm,)
        elif t == "function_definition":
            fd = _find_function_declarator(node.child_by_field_name("declarator"))
            if fd is not None:
                raw = _txt(src, fd.child_by_field_name("declarator")).replace(" ", "")
                qual = "::".join(scope + (raw,)) if scope else raw
                body = node.child_by_field_name("body")
                sig_end = body.start_byte if body is not None else node.end_byte
                sig = norm_ws(src[node.start_byte:sig_end].decode("utf-8", errors="replace"))
                full = norm_ws(_txt(src, node))
                out.functions.append(FuncDef(qual, raw.split("::")[-1], node.start_point.row + 1,
                                             node.end_point.row + 1, sig,
                                             hashlib.sha1(full.encode()).hexdigest()))
                child_fn = qual
        elif t in ("declaration", "field_declaration") and fn is None:
            fd = _find_function_declarator(node.child_by_field_name("declarator"))
            if fd is not None:
                raw = _txt(src, fd.child_by_field_name("declarator")).replace(" ", "")
                qual = "::".join(scope + (raw,)) if scope else raw
                out.decls.append(FuncDecl(qual, node.start_point.row + 1, norm_ws(_txt(src, node))))
        elif t in ("preproc_def", "preproc_function_def"):
            name = _txt(src, node.child_by_field_name("name"))
            if name:
                out.macros.append(MacroDef(name, node.start_point.row + 1, norm_ws(_txt(src, node))))
        elif t == "preproc_include":
            p = _txt(src, node.child_by_field_name("path")).strip()
            if len(p) >= 2 and p[0] in "\"<":
                out.includes.append(p[1:-1])
        elif t == "call_expression":
            callee = _callee_name(src, node.child_by_field_name("function"))
            if callee:
                out.calls.append(CallSite(fn, callee, node.start_point.row + 1))
        elif t == "field_expression":
            fld = node.child_by_field_name("field")
            if fld is not None and (node.parent is None or node.parent.type != "call_expression"
                                    or node.parent.child_by_field_name("function").id != node.id):
                out.members.append(MemberRef(fn, _txt(src, fld), node.start_point.row + 1,
                                             _is_write_target(node)))
        for ch in reversed(node.children):
            stack.append((ch, child_scope, child_fn))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_cparse.py -q`
Expected: `5 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `9 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_cparse.py backend/codetortoise/cparse.py
git commit -m "feat(backend): tree-sitter C/C++ structural parser"
```

---

### Task 3: Change-set model, git fixture source, bundled C/C++ fixture

Defines the VCS-neutral `ChangeSet` and the CL stacking rule (several CLs touching one file chain
before→after in CL order). Adds the bundled fixture used by every later test and by `fixture-demo`: a small
layered C codebase (`include/hal` → `hal` → `driver` → `service` → `app`, plus a C++ `cpp/` module) and two
"CLs" stored as overlay directories:

- **CL 101** — `uart_send` gains an overflow path returning `-2` and writes `u->errors` / `u->stats.tx`
  through local aliases (`int *err = &u->errors; *err += 1;`, `struct Stats *st = &u->stats; st->tx++;`).
- **CL 102** — `struct Uart` gains a field (layout change) and `hal_write` takes `unsigned reg` (prototype + definition).

`build_fixture()` materializes them as a git repo whose commits are named `CL <n>: …`, checks out the base
commit (the "base workspace") and writes `compile_commands.json`. `GitFixtureSource` implements the `Source`
protocol over it, including drift detection.

**Files:**
- Create: `backend/codetortoise/fixtures/cfixture/base/include/hal/regs.h`
- Create: `backend/codetortoise/fixtures/cfixture/base/hal/regs.c`
- Create: `backend/codetortoise/fixtures/cfixture/base/driver/uart.h`
- Create: `backend/codetortoise/fixtures/cfixture/base/driver/uart.c`
- Create: `backend/codetortoise/fixtures/cfixture/base/service/logger.h`
- Create: `backend/codetortoise/fixtures/cfixture/base/service/logger.c`
- Create: `backend/codetortoise/fixtures/cfixture/base/app/main.c`
- Create: `backend/codetortoise/fixtures/cfixture/base/cpp/engine.h`
- Create: `backend/codetortoise/fixtures/cfixture/base/cpp/engine.cpp`
- Create: `backend/codetortoise/fixtures/cfixture/cl101/driver/uart.c`
- Create: `backend/codetortoise/fixtures/cfixture/cl102/driver/uart.h`
- Create: `backend/codetortoise/fixtures/cfixture/cl102/include/hal/regs.h`
- Create: `backend/codetortoise/fixtures/cfixture/cl102/hal/regs.c`
- Create: `backend/codetortoise/vcs/__init__.py`
- Create: `backend/codetortoise/vcs/model.py`
- Create: `backend/codetortoise/vcs/source.py`
- Create: `backend/codetortoise/vcs/gitfixture.py`
- Create: `backend/codetortoise/fixture.py`
- Test: `backend/tests/conftest.py`
- Test: `backend/tests/test_vcs_model.py`
- Test: `backend/tests/test_gitfixture.py`

**Interfaces:**
- Produces `codetortoise.vcs.model`: `ClMeta(cl, status: "pending"|"submitted", user, description)`,
  `PerClText(cl, before, after)`, `FileChange(depot, local, action, before, after, base_rev, per_cl)`,
  `DriftItem(depot, local, expected, actual)`, `ChangeSet(cls, files, drift)`,
  `stack(per_cl: list[tuple[ClMeta, list[FileChange]]]) -> list[FileChange]`.
- Produces `codetortoise.vcs.source`: `Source` protocol with `load(cls: list[int]) -> ChangeSet`; `SourceError`.
- Produces `codetortoise.vcs.gitfixture.GitFixtureSource(repo: Path)`.
- Produces `codetortoise.fixture`: `build_fixture(dest: Path) -> FixtureWorkspace(root, compile_commands, cls)`,
  `CL_DESCRIPTIONS`, `FIXTURE_SRC`.
- Produces test fixtures in `tests/conftest.py`: `fx` (FixtureWorkspace), `fx_source` (GitFixtureSource).
- `FileChange.local` is always `canon()`-ed.

- [ ] **Step 1: Create project files**

`backend/codetortoise/fixtures/cfixture/base/include/hal/regs.h`:

```c
#ifndef HAL_REGS_H
#define HAL_REGS_H

#define REG_CTRL 0
#define REG_STATUS 1

struct Regs {
    int ctrl;
    int status;
};

int hal_read(struct Regs *r, int reg);
int hal_write(struct Regs *r, int reg, int value);

#endif
```

`backend/codetortoise/fixtures/cfixture/base/hal/regs.c`:

```c
#include "hal/regs.h"

int hal_read(struct Regs *r, int reg)
{
    if (reg == REG_CTRL)
        return r->ctrl;
    return r->status;
}

int hal_write(struct Regs *r, int reg, int value)
{
    if (reg == REG_CTRL)
        r->ctrl = value;
    else
        r->status = value;
    return 0;
}
```

`backend/codetortoise/fixtures/cfixture/base/driver/uart.h`:

```c
#ifndef DRIVER_UART_H
#define DRIVER_UART_H

#include "hal/regs.h"

struct Stats {
    int tx;
    int rx;
};

struct Uart {
    struct Regs *regs;
    int baud;
    int errors;
    struct Stats stats;
};

int uart_init(struct Uart *u, struct Regs *regs, int baud);
int uart_send(struct Uart *u, const char *buf, int len);
int uart_errors(const struct Uart *u);

#endif
```

`backend/codetortoise/fixtures/cfixture/base/driver/uart.c`:

```c
#include "driver/uart.h"

int uart_init(struct Uart *u, struct Regs *regs, int baud)
{
    u->regs = regs;
    u->baud = baud;
    u->errors = 0;
    return hal_write(regs, REG_CTRL, baud);
}

int uart_send(struct Uart *u, const char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++)
        hal_write(u->regs, REG_STATUS, buf[i]);
    return 0;
}

int uart_errors(const struct Uart *u)
{
    return u->errors;
}
```

`backend/codetortoise/fixtures/cfixture/base/service/logger.h`:

```c
#ifndef SERVICE_LOGGER_H
#define SERVICE_LOGGER_H

#include "driver/uart.h"

struct Logger {
    struct Uart *uart;
    int dropped;
};

int logger_init(struct Logger *lg, struct Uart *u);
int logger_write(struct Logger *lg, const char *msg, int len);
void logger_flush(struct Logger *lg);

#endif
```

`backend/codetortoise/fixtures/cfixture/base/service/logger.c`:

```c
#include "service/logger.h"

int logger_init(struct Logger *lg, struct Uart *u)
{
    lg->uart = u;
    lg->dropped = 0;
    return 0;
}

int logger_write(struct Logger *lg, const char *msg, int len)
{
    if (uart_send(lg->uart, msg, len) != 0) {
        lg->dropped++;
        return -1;
    }
    return 0;
}

void logger_flush(struct Logger *lg)
{
    uart_send(lg->uart, "\n", 1);
}
```

`backend/codetortoise/fixtures/cfixture/base/app/main.c`:

```c
#include "service/logger.h"

static struct Regs g_regs;
static struct Uart g_uart;
static struct Logger g_log;

int main(void)
{
    uart_init(&g_uart, &g_regs, 115200);
    logger_init(&g_log, &g_uart);
    logger_write(&g_log, "hello", 5);
    logger_flush(&g_log);
    return uart_errors(&g_uart);
}
```

`backend/codetortoise/fixtures/cfixture/base/cpp/engine.h`:

```c
#ifndef CPP_ENGINE_H
#define CPP_ENGINE_H

struct Inner {
    int n;
};

struct State {
    Inner inner;
    int x;
};

namespace svc {

class Base {
public:
    virtual ~Base();
    virtual int base(State &s);
};

class Engine : public Base {
public:
    int step(State &st);
    int base(State &s) override;
    int level = 0;
};

}  // namespace svc

#endif
```

`backend/codetortoise/fixtures/cfixture/base/cpp/engine.cpp`:

```cpp
#include "cpp/engine.h"

namespace svc {

Base::~Base() {}

int Base::base(State &s)
{
    return s.x;
}

int Engine::base(State &s)
{
    s.x = 1;
    return 1;
}

int Engine::step(State &st)
{
    auto &r = st.inner;
    r.n += 2;
    level = 3;
    return base(st) + 1;
}

}  // namespace svc
```

`backend/codetortoise/fixtures/cfixture/cl101/driver/uart.c`:

```c
#include "driver/uart.h"

int uart_init(struct Uart *u, struct Regs *regs, int baud)
{
    u->regs = regs;
    u->baud = baud;
    u->errors = 0;
    return hal_write(regs, REG_CTRL, baud);
}

int uart_send(struct Uart *u, const char *buf, int len)
{
    int i;
    struct Stats *st = &u->stats;
    int *err = &u->errors;
    if (len > 64) {
        *err += 1;
        return -2;
    }
    for (i = 0; i < len; i++) {
        hal_write(u->regs, REG_STATUS, buf[i]);
        st->tx++;
    }
    return 0;
}

int uart_errors(const struct Uart *u)
{
    return u->errors;
}
```

`backend/codetortoise/fixtures/cfixture/cl102/driver/uart.h`:

```c
#ifndef DRIVER_UART_H
#define DRIVER_UART_H

#include "hal/regs.h"

struct Stats {
    int tx;
    int rx;
};

struct Uart {
    struct Regs *regs;
    int flags;
    int baud;
    int errors;
    struct Stats stats;
};

int uart_init(struct Uart *u, struct Regs *regs, int baud);
int uart_send(struct Uart *u, const char *buf, int len);
int uart_errors(const struct Uart *u);

#endif
```

`backend/codetortoise/fixtures/cfixture/cl102/include/hal/regs.h`:

```c
#ifndef HAL_REGS_H
#define HAL_REGS_H

#define REG_CTRL 0
#define REG_STATUS 1

struct Regs {
    int ctrl;
    int status;
};

int hal_read(struct Regs *r, int reg);
int hal_write(struct Regs *r, unsigned reg, int value);

#endif
```

`backend/codetortoise/fixtures/cfixture/cl102/hal/regs.c`:

```c
#include "hal/regs.h"

int hal_read(struct Regs *r, int reg)
{
    if (reg == REG_CTRL)
        return r->ctrl;
    return r->status;
}

int hal_write(struct Regs *r, unsigned reg, int value)
{
    if (reg == REG_CTRL)
        r->ctrl = value;
    else
        r->status = value;
    return 0;
}
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/conftest.py`:

```python
import pytest

from codetortoise.fixture import build_fixture
from codetortoise.vcs.gitfixture import GitFixtureSource


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """Git-backed fixture workspace checked out at the base commit (CLs 101 and 102 exist as commits)."""
    return build_fixture(tmp_path_factory.mktemp("fixture"))


@pytest.fixture(scope="session")
def fx_source(fx):
    return GitFixtureSource(fx.root)
```

`backend/tests/test_vcs_model.py`:

```python
from codetortoise.vcs.model import ClMeta, FileChange, stack


def fc(depot, action, before, after):
    return FileChange(depot=depot, local="/w/" + depot[2:], action=action, before=before, after=after)


def test_stack_chains_same_file_across_cls_in_cl_order():
    m1, m2 = ClMeta(cl=5, status="pending"), ClMeta(cl=3, status="submitted")
    files = stack([(m1, [fc("//d/a.c", "edit", "v2", "v3")]),
                   (m2, [fc("//d/a.c", "edit", "v1", "v2"), fc("//d/b.c", "add", "", "b")])])
    a, b = files
    assert (a.depot, a.before, a.after) == ("//d/a.c", "v1", "v3")
    assert [p.cl for p in a.per_cl] == [3, 5]
    assert (b.action, b.before, b.after) == ("add", "", "b")


def test_stack_delete_wins_and_readd_is_edit():
    m1, m2, m3 = (ClMeta(cl=i, status="pending") for i in (1, 2, 3))
    files = stack([(m1, [fc("//d/a.c", "edit", "v1", "v2")]), (m2, [fc("//d/a.c", "delete", "v2", "")])])
    assert files[0].action == "delete" and files[0].after == ""
    files = stack([(m2, [fc("//d/a.c", "delete", "v1", "")]), (m3, [fc("//d/a.c", "add", "", "new")])])
    assert files[0].action == "edit" and files[0].after == "new"
```

`backend/tests/test_gitfixture.py`:

```python
import shutil

import pytest

from codetortoise.vcs.gitfixture import GitFixtureSource
from codetortoise.vcs.source import SourceError


def test_loads_cls_sorted_with_before_after(fx_source, fx):
    cs = fx_source.load([102, 101])
    assert [c.cl for c in cs.cls] == [101, 102]
    assert cs.cls[0].description == "uart: count tx stats and report overflow"
    depots = [f.depot for f in cs.files]
    assert depots == ["//fixture/driver/uart.c", "//fixture/driver/uart.h", "//fixture/hal/regs.c",
                      "//fixture/include/hal/regs.h"]
    uart_c = cs.files[0]
    assert uart_c.action == "edit"
    assert "return -2;" in uart_c.after and "return -2;" not in uart_c.before
    assert uart_c.local == str((fx.root / "driver/uart.c").resolve())
    assert cs.drift == []


def test_unknown_cl_raises(fx_source):
    with pytest.raises(SourceError, match="CL 999 not found"):
        fx_source.load([999])


def test_drift_when_workspace_differs(tmp_path, fx):
    ws = tmp_path / "ws"
    shutil.copytree(fx.root, ws, symlinks=True)
    (ws / "driver/uart.c").write_text("/* locally modified */\n")
    cs = GitFixtureSource(ws).load([101])
    assert [d.depot for d in cs.drift] == ["//fixture/driver/uart.c"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_vcs_model.py tests/test_gitfixture.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.fixture'`

- [ ] **Step 4: Implement**

`backend/codetortoise/vcs/__init__.py` — empty file.

`backend/codetortoise/vcs/model.py`:

```python
"""Change-set model shared by all VCS sources."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClMeta(BaseModel):
    cl: int
    status: Literal["pending", "submitted"]
    user: str = ""
    description: str = ""


class PerClText(BaseModel):
    cl: int
    before: str
    after: str


class FileChange(BaseModel):
    depot: str
    local: str
    action: str                 # add | edit | delete | move/add | move/delete | integrate | branch
    before: str                 # content before the first CL touching this file ("" if added)
    after: str                  # content after the last CL touching this file ("" if deleted)
    base_rev: str | None = None  # revision the first CL is based on (p4: "#N"; git: commit sha)
    per_cl: list[PerClText] = Field(default_factory=list)


class DriftItem(BaseModel):
    depot: str
    local: str
    expected: str
    actual: str


class ChangeSet(BaseModel):
    cls: list[ClMeta]
    files: list[FileChange]
    drift: list[DriftItem] = Field(default_factory=list)


def stack(per_cl: list[tuple[ClMeta, list[FileChange]]]) -> list[FileChange]:
    """Combine per-CL file changes (sorted by CL number) into cumulative changes.

    For a file touched by several CLs: before = first CL's before, after = last CL's after,
    per_cl keeps each CL's own before/after.
    """
    merged: dict[str, FileChange] = {}
    for meta, files in sorted(per_cl, key=lambda x: x[0].cl):
        for f in files:
            step = PerClText(cl=meta.cl, before=f.before, after=f.after)
            if f.depot not in merged:
                merged[f.depot] = f.model_copy(update={"per_cl": [step]})
            else:
                m = merged[f.depot]
                action = m.action
                if f.action == "delete":
                    action = "delete"
                elif action == "delete":
                    action = "edit"
                merged[f.depot] = m.model_copy(update={"after": f.after, "action": action,
                                                       "per_cl": m.per_cl + [step]})
    return sorted(merged.values(), key=lambda f: f.depot)
```

`backend/codetortoise/vcs/source.py`:

```python
"""VCS source protocol."""
from __future__ import annotations

from typing import Protocol

from codetortoise.vcs.model import ChangeSet


class SourceError(RuntimeError):
    pass


class Source(Protocol):
    def load(self, cls: list[int]) -> ChangeSet: ...
```

`backend/codetortoise/vcs/gitfixture.py`:

```python
"""Git-backed Source for development and tests.

A "CL" is a commit whose subject starts with "CL <number>". The workspace root is a
working tree (normally checked out at the base commit) and is never modified.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from codetortoise.paths import canon
from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, stack
from codetortoise.vcs.source import SourceError

_ACTIONS = {"A": "add", "M": "edit", "D": "delete"}


class GitFixtureSource:
    def __init__(self, repo: Path):
        self.repo = Path(repo)

    def _git(self, *args: str) -> str:
        r = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise SourceError(f"git {' '.join(args)}: {r.stderr.strip()}")
        return r.stdout

    def _commit_for(self, cl: int) -> tuple[str, str]:
        out = self._git("log", "--all", "--format=%H%x00%s")
        for line in out.splitlines():
            sha, _, subject = line.partition("\x00")
            head, _, desc = subject.partition(":")
            if head.strip() == f"CL {cl}":
                return sha, desc.strip()
        raise SourceError(f"CL {cl} not found")

    def _show(self, rev: str, path: str) -> str:
        r = subprocess.run(["git", "-C", str(self.repo), "show", f"{rev}:{path}"], capture_output=True)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""

    def load(self, cls: list[int]) -> ChangeSet:
        per_cl = []
        metas = []
        for cl in sorted(set(cls)):
            sha, desc = self._commit_for(cl)
            meta = ClMeta(cl=cl, status="submitted", user="fixture", description=desc)
            metas.append(meta)
            files = []
            for line in self._git("diff-tree", "--no-commit-id", "-r", "--name-status", sha).splitlines():
                status, _, path = line.partition("\t")
                action = _ACTIONS.get(status[:1], "edit")
                files.append(FileChange(
                    depot=f"//fixture/{path}", local=canon(str(self.repo / path)), action=action,
                    before="" if action == "add" else self._show(f"{sha}^", path),
                    after="" if action == "delete" else self._show(sha, path),
                    base_rev=f"{sha}^"))
            per_cl.append((meta, files))
        files = stack(per_cl)
        return ChangeSet(cls=metas, files=files, drift=self._drift(files))

    def _drift(self, files: list[FileChange]) -> list[DriftItem]:
        out = []
        for f in files:
            p = Path(f.local)
            actual = p.read_text(errors="replace") if p.exists() else ""
            if f.action != "add" and actual != f.before:
                out.append(DriftItem(depot=f.depot, local=f.local, expected=f.base_rev or "",
                                     actual="workspace content differs from CL base"))
        return out
```

`backend/codetortoise/fixture.py`:

```python
"""Builds the bundled C/C++ fixture as a git-backed workspace (tests and demo)."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FIXTURE_SRC = Path(__file__).parent / "fixtures" / "cfixture"
CL_DESCRIPTIONS = {
    101: "uart: count tx stats and report overflow",
    102: "uart: add flags field; hal_write takes unsigned reg",
}


@dataclass
class FixtureWorkspace:
    root: Path
    compile_commands: Path
    cls: list[int]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def build_fixture(dest: Path) -> FixtureWorkspace:
    root = Path(dest) / "ws"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(FIXTURE_SRC / "base", root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    for cl, desc in sorted(CL_DESCRIPTIONS.items()):
        shutil.copytree(FIXTURE_SRC / f"cl{cl}", root, dirs_exist_ok=True)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"CL {cl}: {desc}")
    _git(root, "checkout", "-q", base)
    entries = []
    for src in sorted(root.rglob("*")):
        if src.suffix not in (".c", ".cpp") or ".git" in src.parts:
            continue
        lang = ["-xc"] if src.suffix == ".c" else ["-xc++", "-std=c++17"]
        entries.append({"directory": str(root), "file": str(src),
                        "arguments": ["clang", *lang, "-Iinclude", "-I.", "-c", str(src),
                                      "-o", str(src.with_suffix(".o"))]})
    cc = root / "compile_commands.json"
    cc.write_text(json.dumps(entries, indent=2))
    return FixtureWorkspace(root=root, compile_commands=cc, cls=sorted(CL_DESCRIPTIONS))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_vcs_model.py tests/test_gitfixture.py -q`
Expected: `5 passed`

- [ ] **Step 6: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `14 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/codetortoise/fixtures/cfixture/base/include/hal/regs.h backend/codetortoise/fixtures/cfixture/base/hal/regs.c backend/codetortoise/fixtures/cfixture/base/driver/uart.h backend/codetortoise/fixtures/cfixture/base/driver/uart.c backend/codetortoise/fixtures/cfixture/base/service/logger.h backend/codetortoise/fixtures/cfixture/base/service/logger.c backend/codetortoise/fixtures/cfixture/base/app/main.c backend/codetortoise/fixtures/cfixture/base/cpp/engine.h backend/codetortoise/fixtures/cfixture/base/cpp/engine.cpp backend/codetortoise/fixtures/cfixture/cl101/driver/uart.c backend/codetortoise/fixtures/cfixture/cl102/driver/uart.h backend/codetortoise/fixtures/cfixture/cl102/include/hal/regs.h backend/codetortoise/fixtures/cfixture/cl102/hal/regs.c backend/tests/conftest.py backend/tests/test_vcs_model.py backend/tests/test_gitfixture.py backend/codetortoise/vcs/__init__.py backend/codetortoise/vcs/model.py backend/codetortoise/vcs/source.py backend/codetortoise/vcs/gitfixture.py backend/codetortoise/fixture.py
git commit -m "feat(backend): change-set model, git fixture source and bundled C/C++ fixture"
```

---

### Task 4: Perforce runner and source

`P4Runner` is the only code that runs `p4`. It allowlists read-only commands (plus `login -p` for
credential checks, which prints the ticket instead of writing the host's tickets file) and parses `-G`
(Python marshal) output. `P4Source` reads shelved CLs (`describe -S`, base `#rev`, shelf `@=CL`) and
submitted CLs (`#rev-1` → `#rev`), maps depot → local with `where`, skips binary content, stacks CLs and reports
drift by comparing `p4 have` against each file's base revision. Tests use a fake runner; no Perforce server is needed.

**Files:**
- Create: `backend/codetortoise/vcs/p4runner.py`
- Create: `backend/codetortoise/vcs/p4source.py`
- Test: `backend/tests/test_p4source.py`

**Interfaces:**
- Consumes: `vcs.model.*`, `vcs.source.SourceError`, `paths.canon`.
- Produces: `P4Runner(p4port, client, p4_bin="p4", timeout=120)` with `run(command, *args) -> list[dict]`,
  `print_text(filespec) -> str`, `login_check(user, password) -> str` (ticket); `P4Error`; `unmarshal_all(bytes) -> list[dict]`;
  `READ_ONLY` command set.
- Produces: `P4Source(runner)` implementing `Source`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_p4source.py`:

```python
import marshal

import pytest

from codetortoise.vcs.p4runner import P4Error, P4Runner, unmarshal_all
from codetortoise.vcs.p4source import P4Source
from codetortoise.vcs.source import SourceError


class FakeP4:
    """Stands in for P4Runner: canned `run` records and file contents."""

    def __init__(self, describe, files, have=None, where_root="/ws"):
        self.describe = describe
        self.files = files
        self.have = have or {}
        self.where_root = where_root
        self.calls = []

    def run(self, command, *args):
        self.calls.append((command, *args))
        if command == "describe":
            cl = int(args[-1])
            return [self.describe[(cl, "-S" in args)]]
        if command == "where":
            return [{"depotFile": d, "path": self.where_root + d[len("//depot"):]} for d in args]
        if command == "have":
            if args[0] not in self.have:
                raise P4Error("file(s) not on client")
            return [{"haveRev": self.have[args[0]]}]
        raise AssertionError(command)

    def print_text(self, spec):
        return self.files[spec]


def test_shelved_cl_reads_base_rev_and_shelf():
    p4 = FakeP4(
        describe={(7, False): {"status": "pending", "user": "bob", "desc": "fix\n"},
                  (7, True): {"status": "pending", "user": "bob", "desc": "fix\n",
                              "depotFile0": "//depot/a.c", "action0": "edit", "rev0": "4", "type0": "text",
                              "depotFile1": "//depot/n.c", "action1": "add", "rev1": "none", "type1": "text",
                              "depotFile2": "//depot/img.bin", "action2": "edit", "rev2": "2", "type2": "binary"}},
        files={"//depot/a.c#4": "old", "//depot/a.c@=7": "new", "//depot/n.c@=7": "added"},
        have={"//depot/a.c": "4", "//depot/img.bin": "2"})
    cs = P4Source(p4).load([7])
    assert cs.cls[0].status == "pending" and cs.cls[0].description == "fix"
    a, img, n = cs.files
    assert (a.before, a.after, a.base_rev, a.local) == ("old", "new", "#4", "/ws/a.c")
    assert (n.action, n.before, n.after, n.base_rev) == ("add", "", "added", None)
    assert (img.before, img.after) == ("", "")  # binary content never fetched
    assert cs.drift == []


def test_submitted_cl_uses_previous_revision_and_reports_drift():
    p4 = FakeP4(
        describe={(9, False): {"status": "submitted", "user": "amy", "desc": "x",
                               "depotFile0": "//depot/a.c", "action0": "edit", "rev0": "5", "type0": "text"}},
        files={"//depot/a.c#4": "v4", "//depot/a.c#5": "v5"}, have={"//depot/a.c": "3"})
    cs = P4Source(p4).load([9])
    f = cs.files[0]
    assert (f.before, f.after, f.base_rev) == ("v4", "v5", "#4")
    assert [(d.expected, d.actual) for d in cs.drift] == [("#4", "#3")]


def test_pending_without_shelved_files_is_error():
    p4 = FakeP4(describe={(3, False): {"status": "pending"}, (3, True): {"status": "pending"}}, files={})
    with pytest.raises(SourceError, match="no shelved files"):
        P4Source(p4).load([3])


def test_runner_refuses_mutating_commands():
    with pytest.raises(P4Error, match="not allowed"):
        P4Runner("p4:1666", "ws").run("submit", "-c", "1")


def test_unmarshal_all_decodes_records():
    data = marshal.dumps({b"code": b"stat", b"change": b"12"}) + marshal.dumps({b"code": b"error", b"data": b"no"})
    assert unmarshal_all(data) == [{"code": "stat", "change": "12"}, {"code": "error", "data": "no"}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_p4source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.vcs.p4runner'`

- [ ] **Step 3: Implement**

`backend/codetortoise/vcs/p4runner.py`:

```python
"""The only way CodeTortoise talks to Perforce. Allowlists read-only commands (+ login -p)."""
from __future__ import annotations

import io
import marshal
import subprocess

READ_ONLY = frozenset({"describe", "print", "where", "have", "client", "info", "changes", "fstat", "files"})


class P4Error(RuntimeError):
    pass


def _dec(v):
    return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v


def unmarshal_all(data: bytes) -> list[dict]:
    out = []
    buf = io.BytesIO(data)
    while True:
        try:
            d = marshal.load(buf)
        except EOFError:
            break
        out.append({_dec(k): _dec(v) for k, v in d.items()})
    return out


class P4Runner:
    def __init__(self, p4port: str, client: str | None, p4_bin: str = "p4", timeout: float = 120):
        self.p4port = p4port
        self.client = client
        self.p4_bin = p4_bin
        self.timeout = timeout

    def _base(self, user: str | None = None) -> list[str]:
        cmd = [self.p4_bin, "-p", self.p4port]
        if self.client:
            cmd += ["-c", self.client]
        if user:
            cmd += ["-u", user]
        return cmd

    def run(self, command: str, *args: str) -> list[dict]:
        if command not in READ_ONLY:
            raise P4Error(f"p4 {command} is not allowed (read-only runner)")
        try:
            r = subprocess.run(self._base() + ["-G", command, *args], capture_output=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise P4Error(f"p4 {command}: {e}") from e
        records = unmarshal_all(r.stdout)
        errors = [d.get("data", "").strip() for d in records if d.get("code") == "error"]
        if errors:
            raise P4Error(f"p4 {command}: {'; '.join(errors)}")
        if r.returncode != 0 and not records:
            raise P4Error(f"p4 {command}: {r.stderr.decode(errors='replace').strip()}")
        return [d for d in records if d.get("code") == "stat"]

    def print_text(self, filespec: str) -> str:
        try:
            r = subprocess.run(self._base() + ["print", "-q", filespec], capture_output=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise P4Error(f"p4 print {filespec}: {e}") from e
        if r.returncode != 0:
            raise P4Error(f"p4 print {filespec}: {r.stderr.decode(errors='replace').strip()}")
        return r.stdout.decode("utf-8", errors="replace")

    def login_check(self, user: str, password: str) -> str:
        """Validates credentials. Returns the ticket (printed, not stored in the tickets file)."""
        try:
            r = subprocess.run(self._base(user) + ["login", "-p"], input=(password + "\n").encode(),
                               capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise P4Error(f"p4 login: {e}") from e
        if r.returncode != 0:
            raise P4Error("p4 login failed: " + (r.stderr or r.stdout).decode(errors="replace").strip())
        lines = [l.strip() for l in r.stdout.decode(errors="replace").splitlines() if l.strip()]
        return lines[-1] if lines else ""
```

`backend/codetortoise/vcs/p4source.py`:

```python
"""Perforce Source: shelved (pending) and submitted CLs, read-only against the base workspace."""
from __future__ import annotations

from codetortoise.paths import canon
from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, stack
from codetortoise.vcs.p4runner import P4Error, P4Runner
from codetortoise.vcs.source import SourceError

_NO_BEFORE = {"add", "branch", "move/add", "import"}
_NO_AFTER = {"delete", "move/delete", "purge", "archive"}


def _indexed(d: dict, prefix: str) -> list[str]:
    out = []
    i = 0
    while f"{prefix}{i}" in d:
        out.append(d[f"{prefix}{i}"])
        i += 1
    return out


class P4Source:
    def __init__(self, runner: P4Runner):
        self.p4 = runner

    def _describe(self, cl: int) -> tuple[ClMeta, dict, bool]:
        recs = self.p4.run("describe", "-s", str(cl))
        if not recs:
            raise SourceError(f"CL {cl} not found")
        d = recs[0]
        status = d.get("status", "")
        shelved = status != "submitted"
        if shelved:
            recs = self.p4.run("describe", "-s", "-S", str(cl))
            d = recs[0] if recs else d
            if "depotFile0" not in d:
                raise SourceError(f"CL {cl} is pending with no shelved files")
        meta = ClMeta(cl=cl, status="submitted" if not shelved else "pending", user=d.get("user", ""),
                      description=d.get("desc", "").strip())
        return meta, d, shelved

    def _files(self, cl: int, d: dict, shelved: bool) -> list[FileChange]:
        depots, actions, revs = _indexed(d, "depotFile"), _indexed(d, "action"), _indexed(d, "rev")
        types = _indexed(d, "type")
        where = {r.get("depotFile"): r.get("path") for r in self.p4.run("where", *depots)} if depots else {}
        out = []
        for i, depot in enumerate(depots):
            action = actions[i]
            rev = int(revs[i]) if i < len(revs) and revs[i].isdigit() else 0
            binary = i < len(types) and "binary" in types[i]
            base_rev = rev if shelved else rev - 1
            before = after = ""
            if not binary:
                if action not in _NO_BEFORE and base_rev > 0:
                    before = self.p4.print_text(f"{depot}#{base_rev}")
                if action not in _NO_AFTER:
                    after = self.p4.print_text(f"{depot}@={cl}" if shelved else f"{depot}#{rev}")
            local = where.get(depot)
            out.append(FileChange(depot=depot, local=canon(local) if local else "", action=action, before=before,
                                  after=after, base_rev=f"#{base_rev}" if base_rev > 0 else None))
        return out

    def _drift(self, files: list[FileChange]) -> list[DriftItem]:
        out = []
        for f in files:
            if f.base_rev is None:
                continue
            try:
                recs = self.p4.run("have", f.depot)
                actual = f"#{recs[0].get('haveRev')}" if recs else "not synced"
            except P4Error:
                actual = "not synced"
            if actual != f.base_rev:
                out.append(DriftItem(depot=f.depot, local=f.local, expected=f.base_rev, actual=actual))
        return out

    def load(self, cls: list[int]) -> ChangeSet:
        per_cl, metas = [], []
        try:
            for cl in sorted(set(cls)):
                meta, d, shelved = self._describe(cl)
                metas.append(meta)
                per_cl.append((meta, self._files(cl, d, shelved)))
            files = stack(per_cl)
            return ChangeSet(cls=metas, files=files, drift=self._drift(files))
        except P4Error as e:
            raise SourceError(str(e)) from e
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_p4source.py -q`
Expected: `5 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `19 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_p4source.py backend/codetortoise/vcs/p4runner.py backend/codetortoise/vcs/p4source.py
git commit -m "feat(backend): read-only Perforce runner and P4 source with drift detection"
```

---

### Task 5: DiffMap: hunks → changed functions, types, macros, prototypes

Compares tree-sitter parses of each changed file's before/after text. Functions are matched by
qualified name (overloads by occurrence order) and classified `added | removed | body_modified | signature_changed`
by comparing whitespace-normalized text hashes and signatures. Also records struct/class/enum, macro and
prototype (`decl_*`) changes, and the member names each changed function writes (used to pick TUs that touch the same fields).

**Files:**
- Create: `backend/codetortoise/diffmap.py`
- Test: `backend/tests/test_diffmap.py`

**Interfaces:**
- Consumes: `cparse.parse_source`, `vcs.model.ChangeSet`.
- Produces: `map_changes(cs: ChangeSet) -> DiffMap`; `DiffMap(functions: list[FunctionChange], types: list[TypeChange],
  changed_files: list[str])`; `FunctionChange(file, depot, qualname, name, kind, before_lines, after_lines,
  signature_before, signature_after, written_members)`; `TypeChange(file, depot, name, kind)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_diffmap.py`:

```python
from codetortoise.diffmap import map_changes
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def test_cl101_body_change_with_written_members(fx_source):
    dm = map_changes(fx_source.load([101]))
    assert [(f.qualname, f.kind, f.written_members) for f in dm.functions] == [("uart_send", "body_modified", ["tx"])]
    assert dm.types == []


def test_cl102_signature_type_and_decl_changes(fx_source):
    dm = map_changes(fx_source.load([102]))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("hal_write", "signature_changed")]
    assert sorted((t.name, t.kind) for t in dm.types) == [("Uart", "type_changed"), ("hal_write", "decl_changed")]


def test_added_removed_and_non_source_files():
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/x.c", local="/w/x.c", action="edit",
                   before="int a(void){return 1;}\nint b(void){return 2;}\n",
                   after="int b(void){return 2;}\nint c(void){return 3;}\n"),
        FileChange(depot="//d/README.txt", local="/w/README.txt", action="edit", before="a", after="b")])
    dm = map_changes(cs)
    assert sorted((f.qualname, f.kind) for f in dm.functions) == [("a", "removed"), ("c", "added")]
    assert dm.changed_files == ["/w/x.c"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_diffmap.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.diffmap'`

- [ ] **Step 3: Implement**

`backend/codetortoise/diffmap.py`:

```python
"""Maps a ChangeSet to changed functions / types / macros using tree-sitter."""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.cparse import FuncDef, is_source, parse_source
from codetortoise.vcs.model import ChangeSet

FunctionChangeKind = Literal["added", "removed", "body_modified", "signature_changed"]
TypeChangeKind = Literal["type_added", "type_removed", "type_changed",
                         "macro_added", "macro_removed", "macro_changed",
                         "decl_added", "decl_removed", "decl_changed"]


class FunctionChange(BaseModel):
    file: str
    depot: str
    qualname: str
    name: str
    kind: FunctionChangeKind
    before_lines: tuple[int, int] | None = None
    after_lines: tuple[int, int] | None = None
    signature_before: str | None = None
    signature_after: str | None = None
    written_members: list[str] = Field(default_factory=list)


class TypeChange(BaseModel):
    file: str
    depot: str
    name: str
    kind: TypeChangeKind


class DiffMap(BaseModel):
    functions: list[FunctionChange] = Field(default_factory=list)
    types: list[TypeChange] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)


def _keyed(funcs: list[FuncDef]) -> dict[tuple[str, int], FuncDef]:
    counts: dict[str, int] = defaultdict(int)
    out = {}
    for f in sorted(funcs, key=lambda f: f.start_line):
        out[(f.qualname, counts[f.qualname])] = f
        counts[f.qualname] += 1
    return out


def _diff_named(before: dict[str, str], after: dict[str, str], prefix: str) -> list[tuple[str, str]]:
    out = []
    for name in sorted(set(before) | set(after)):
        if name not in before:
            out.append((name, f"{prefix}_added"))
        elif name not in after:
            out.append((name, f"{prefix}_removed"))
        elif before[name] != after[name]:
            out.append((name, f"{prefix}_changed"))
    return out


def map_changes(cs: ChangeSet) -> DiffMap:
    dm = DiffMap()
    for fc in cs.files:
        if not is_source(fc.local):
            continue
        dm.changed_files.append(fc.local)
        b = parse_source(fc.local, fc.before)
        a = parse_source(fc.local, fc.after)
        bf, af = _keyed(b.functions), _keyed(a.functions)
        for key in sorted(set(bf) | set(af)):
            fb, fa = bf.get(key), af.get(key)
            if fb is not None and fa is not None and fb.text_hash == fa.text_hash:
                continue
            if fb is None:
                kind = "added"
            elif fa is None:
                kind = "removed"
            elif fb.signature != fa.signature:
                kind = "signature_changed"
            else:
                kind = "body_modified"
            ref = fa or fb
            written = sorted({m.field for pf in (a, b) for m in pf.members
                              if m.is_write and m.fn == ref.qualname})
            dm.functions.append(FunctionChange(
                file=fc.local, depot=fc.depot, qualname=ref.qualname, name=ref.name, kind=kind,
                before_lines=(fb.start_line, fb.end_line) if fb else None,
                after_lines=(fa.start_line, fa.end_line) if fa else None,
                signature_before=fb.signature if fb else None,
                signature_after=fa.signature if fa else None,
                written_members=written))
        for name, kind in _diff_named({t.name: t.text for t in b.types if t.name},
                                      {t.name: t.text for t in a.types if t.name}, "type"):
            dm.types.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind))
        for name, kind in _diff_named({d.qualname: d.text for d in b.decls},
                                      {d.qualname: d.text for d in a.decls}, "decl"):
            dm.types.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind))
        for name, kind in _diff_named({m.name: m.text for m in b.macros},
                                      {m.name: m.text for m in a.macros}, "macro"):
            dm.types.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind))
    return dm
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_diffmap.py -q`
Expected: `3 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `22 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_diffmap.py backend/codetortoise/diffmap.py
git commit -m "feat(backend): diffmap from change sets to changed functions and types"
```

---

### Task 6: Toolchain: compile DB, driver query, libclang loading

Makes a vendor cross toolchain usable from libclang:

- `CompileDb` loads `compile_commands.json` (`arguments` or `command`), keys entries by canonical path, and
  finds the nearest entry for files without one (headers, new files).
- `sanitize_args` drops the compiler, output/dependency flags and the source file, and absolutizes include/sysroot
  paths (libclang resolves relative paths against the *process* cwd, not the entry's directory).
- `query_driver` runs `<clang> -E -dM -v -x <lang> /dev/null` like clangd's `--query-driver` to capture implicit
  include dirs, predefined macros and the resource dir.
- `load_libclang` loads the vendor `libclang.so` when configured, else the one bundled in the `libclang` wheel.
- `Toolchain.args_for(file)` combines them. When libclang is *not* the vendor's, it adds `-resource-dir`,
  `-isystem` for the driver's dirs and a generated prelude of the driver's macros.

**Files:**
- Create: `backend/codetortoise/toolchain/__init__.py`
- Create: `backend/codetortoise/toolchain/compile_db.py`
- Create: `backend/codetortoise/toolchain/driver.py`
- Create: `backend/codetortoise/toolchain/libclang.py`
- Create: `backend/codetortoise/toolchain/toolchain.py`
- Test: `backend/tests/test_compile_db.py`
- Test: `backend/tests/test_driver_toolchain.py`

**Interfaces:**
- Consumes: `config.ToolchainConfig`, `paths.canon`.
- Produces: `CompileEntry(file, directory, args: tuple)`, `CompileDb(entries)` with `load(path)`, `files()`,
  `entry_for(file)`, `nearest_entry(file)`, `.entries`; `sanitize_args(entry, strip=frozenset()) -> list[str]`.
- Produces: `DriverInfo(include_dirs, defines, resource_dir)`, `target_flags(args)`, `parse_driver_output(stdout, stderr)`,
  `query_driver(driver, target_args, lang) -> DriverInfo` (raises `RuntimeError`).
- Produces: `LibclangInfo(path, version, vendor)`, `load_libclang(path: str | None) -> LibclangInfo` (idempotent).
- Produces: `Toolchain(cfg, cdb, work_dir)` with `prepare()` (idempotent), `args_for(file) -> list[str]`,
  attributes `libclang`, `driver: dict[str, DriverInfo]`, `driver_error`, `strip: set[str]`; `lang_of(path)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_compile_db.py`:

```python
import json

from codetortoise.toolchain.compile_db import CompileDb, CompileEntry, sanitize_args


def test_sanitize_drops_output_and_dep_flags_and_absolutizes_paths():
    e = CompileEntry("/w/src/a.c", "/w/build", (
        "armclang", "--target=arm-none-eabi", "-Iinc", "-I", "../x", "-isystem", "sys", "--sysroot=../sr",
        "-c", "../src/a.c", "-o", "a.o", "-MD", "-MF", "a.d", "-DFOO=1", "-mcpu=cortex-m4", "-Wall"))
    assert sanitize_args(e) == ["--target=arm-none-eabi", "-I/w/build/inc", "-I", "/w/x", "-isystem", "/w/build/sys",
                                "--sysroot=/w/sr", "-DFOO=1", "-mcpu=cortex-m4", "-Wall"]


def test_sanitize_strip_list_matches_exact_and_key_value():
    e = CompileEntry("/w/a.c", "/w", ("cc", "-mvendor-x", "--vendor-opt=3", "-O2", "a.c"))
    assert sanitize_args(e, {"-mvendor-x", "--vendor-opt"}) == ["-O2"]


def test_load_command_strings_and_nearest_entry(tmp_path):
    (tmp_path / "src/sub").mkdir(parents=True)
    cc = tmp_path / "compile_commands.json"
    cc.write_text(json.dumps([
        {"directory": str(tmp_path), "file": "src/a.c", "command": "cc -Iinc -c src/a.c"},
        {"directory": str(tmp_path), "file": "src/sub/b.c", "arguments": ["cc", "-c", "src/sub/b.c"]}]))
    db = CompileDb.load(cc)
    a = str((tmp_path / "src/a.c").resolve())
    assert db.entry_for(a).args == ("cc", "-Iinc", "-c", "src/a.c")
    assert db.nearest_entry(str(tmp_path / "src/a.h")).file == a
    assert db.nearest_entry(str(tmp_path / "src/sub/b.h")).file == str((tmp_path / "src/sub/b.c").resolve())
    assert db.nearest_entry("/elsewhere/z.h") is not None
```

`backend/tests/test_driver_toolchain.py`:

```python
import shutil

import pytest

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry
from codetortoise.toolchain.driver import DriverInfo, parse_driver_output, query_driver, target_flags
from codetortoise.toolchain.toolchain import Toolchain

STDERR = """clang -cc1 version 17.0.0 based upon LLVM
#include "..." search starts here:
#include <...> search starts here:
 /opt/vendor/lib/clang/17/include
 /opt/vendor/sysroot/usr/include
 /opt/vendor/Frameworks (framework directory)
End of search list.
"""


def test_parse_driver_output():
    dirs, defines = parse_driver_output("#define __ARM_ARCH 7\n#define __VENDOR__ 1\n#define EMPTY\n", STDERR)
    assert dirs == ["/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include", "/opt/vendor/Frameworks"]
    assert defines == [("__ARM_ARCH", "7"), ("__VENDOR__", "1"), ("EMPTY", "")]


def test_target_flags_keeps_only_target_affecting_flags():
    args = ["--target=arm-none-eabi", "-DX", "-mcpu=m4", "-I/w", "-target", "armv7", "-std=c11", "-O2", "-mthumb"]
    assert target_flags(args) == ["--target=arm-none-eabi", "-mcpu=m4", "-target", "armv7", "-std=c11", "-mthumb"]


@pytest.mark.skipif(shutil.which("gcc") is None, reason="needs a host compiler to query")
def test_query_real_driver():
    info = query_driver("gcc", [], "c")
    assert info.include_dirs and any(name == "__STDC__" or name == "__GNUC__" for name, _ in info.defines)


def test_args_for_adds_driver_info_when_libclang_is_not_vendor(tmp_path):
    db = CompileDb([CompileEntry("/w/a.c", "/w", ("vcc", "--target=arm", "-c", "a.c"))])
    tc = Toolchain(ToolchainConfig(clang="/opt/vendor/bin/clang"), db, tmp_path)
    tc.driver["c"] = DriverInfo(("/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include"),
                                (("__VENDOR__", "1"),), "/opt/vendor/lib/clang/17")
    tc._preludes["c"] = tmp_path / "prelude-c.h"
    args = tc.args_for("/w/a.c")
    assert args[:1] == ["--target=arm"]
    assert ["-resource-dir", "/opt/vendor/lib/clang/17"] == args[1:3]
    assert "/opt/vendor/lib/clang/17/include" not in args  # builtin headers come via -resource-dir
    assert ["-isystem", "/opt/vendor/sysroot/usr/include"] == args[3:5]
    assert args[5:7] == ["-include", str(tmp_path / "prelude-c.h")]


def test_prepare_loads_bundled_libclang(tmp_path):
    tc = Toolchain(ToolchainConfig(), CompileDb([]), tmp_path)
    tc.prepare()
    assert tc.libclang.version.startswith("clang version") and tc.libclang.vendor is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_compile_db.py tests/test_driver_toolchain.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.toolchain'`

- [ ] **Step 3: Implement**

`backend/codetortoise/toolchain/__init__.py` — empty file.

`backend/codetortoise/toolchain/compile_db.py`:

```python
"""compile_commands.json loading and libclang argument sanitation."""
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from codetortoise.paths import canon

# flags that take a separate value and should be dropped together with it
_DROP_WITH_VALUE = {"-o", "-MF", "-MT", "-MQ", "-MJ", "--serialize-diagnostics"}
_DROP = {"-c", "-M", "-MM", "-MD", "-MMD", "-MP", "-MG", "-Werror", "-fcolor-diagnostics",
         "-fdiagnostics-color", "-pipe"}
# flags whose value is a path that must be made absolute (libclang resolves against process cwd)
_SEP_PATH_FLAGS = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "--sysroot",
                   "-isysroot", "-F"}
_JOINED_PATH_FLAGS = ("-isystem", "-iquote", "-idirafter", "-I", "-F")


@dataclass(frozen=True)
class CompileEntry:
    file: str
    directory: str
    args: tuple[str, ...]


def _abs(directory: str, p: str) -> str:
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(directory, p))


class CompileDb:
    def __init__(self, entries: list[CompileEntry]):
        self.entries = entries
        self._by_file = {e.file: e for e in entries}
        self._by_dir: dict[str, list[CompileEntry]] = {}
        for e in entries:
            self._by_dir.setdefault(os.path.dirname(e.file), []).append(e)

    @classmethod
    def load(cls, path: Path) -> CompileDb:
        raw = json.loads(Path(path).read_text())
        entries = []
        for item in raw:
            directory = item.get("directory", os.path.dirname(str(path)))
            args = item.get("arguments") or shlex.split(item.get("command", ""))
            entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args)))
        return cls(entries)

    def files(self) -> list[str]:
        return list(self._by_file)

    def entry_for(self, file: str) -> CompileEntry | None:
        return self._by_file.get(canon(file))

    def nearest_entry(self, file: str) -> CompileEntry | None:
        """Exact entry, else an entry in the same directory, else the one sharing the longest path prefix."""
        file = canon(file)
        if file in self._by_file:
            return self._by_file[file]
        d = os.path.dirname(file)
        while True:
            if d in self._by_dir:
                return self._by_dir[d][0]
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return self.entries[0] if self.entries else None


def sanitize_args(entry: CompileEntry, strip: set[str] = frozenset()) -> list[str]:
    """Compiler argv -> libclang args: drop compiler, output/dep flags, the source file; absolutize paths."""
    args = list(entry.args[1:])
    out: list[str] = []
    i = 0
    src = entry.file
    while i < len(args):
        a = args[i]
        if a in _DROP_WITH_VALUE:
            i += 2
            continue
        if a in _DROP or a in strip or a.split("=", 1)[0] in strip:
            i += 1
            continue
        if not a.startswith("-") and canon(_abs(entry.directory, a)) == src:
            i += 1
            continue
        if a in _SEP_PATH_FLAGS and i + 1 < len(args):
            out += [a, _abs(entry.directory, args[i + 1])]
            i += 2
            continue
        i += 1
        if a.startswith("--sysroot="):
            out.append("--sysroot=" + _abs(entry.directory, a[len("--sysroot="):]))
            continue
        for flag in _JOINED_PATH_FLAGS:
            if a.startswith(flag) and len(a) > len(flag):
                out.append(flag + _abs(entry.directory, a[len(flag):]))
                break
        else:
            out.append(a)
    return out
```

`backend/codetortoise/toolchain/driver.py`:

```python
"""Query a (vendor) compiler driver for implicit include dirs, predefined macros, resource dir.

Same idea as clangd's --query-driver: lets an upstream libclang parse code meant for a
vendor cross toolchain.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

_TARGET_PREFIXES = ("--target=", "--sysroot", "-isysroot", "-march=", "-mcpu=", "-mfpu=",
                    "-mfloat-abi=", "-mabi=", "-mtune=", "-std=", "-stdlib=")
_TARGET_EXACT = {"-m32", "-m64", "-mthumb", "-marm", "-mbig-endian", "-mlittle-endian"}
_TARGET_WITH_VALUE = {"-target", "--sysroot", "-isysroot"}


@dataclass(frozen=True)
class DriverInfo:
    include_dirs: tuple[str, ...]
    defines: tuple[tuple[str, str], ...]
    resource_dir: str | None


def target_flags(args: list[str]) -> list[str]:
    """Subset of sanitized args that affects the driver's implicit includes/macros."""
    out = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in _TARGET_WITH_VALUE and i + 1 < len(args):
            out += [a, args[i + 1]]
            i += 2
            continue
        if a in _TARGET_EXACT or a.startswith(_TARGET_PREFIXES):
            out.append(a)
        i += 1
    return out


def parse_driver_output(stdout: str, stderr: str) -> tuple[list[str], list[tuple[str, str]]]:
    dirs: list[str] = []
    in_list = False
    for line in stderr.splitlines():
        if line.startswith("#include <...> search starts here:") or line.startswith('#include "..." search starts here:'):
            in_list = True
            continue
        if line.startswith("End of search list."):
            in_list = False
            continue
        if in_list and line.startswith(" "):
            d = line.strip().removesuffix(" (framework directory)")
            if d not in dirs:
                dirs.append(d)
    defines = []
    for line in stdout.splitlines():
        if line.startswith("#define "):
            _, _, rest = line.partition(" ")
            name, _, value = rest.partition(" ")
            defines.append((name, value))
    return dirs, defines


def query_driver(driver: str, target_args: list[str], lang: str, timeout: float = 60) -> DriverInfo:
    """lang: 'c' or 'c++'. Raises RuntimeError if the driver cannot be run."""
    try:
        r = subprocess.run([driver, *target_args, "-E", "-dM", "-v", "-x", lang, "/dev/null"],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"driver query failed: {e}") from e
    if r.returncode != 0:
        raise RuntimeError(f"driver query failed: {r.stderr.strip()[-500:]}")
    dirs, defines = parse_driver_output(r.stdout, r.stderr)
    resource_dir = None
    try:
        rr = subprocess.run([driver, *target_args, "-print-resource-dir"], capture_output=True,
                            text=True, timeout=timeout)
        if rr.returncode == 0 and rr.stdout.strip():
            resource_dir = rr.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return DriverInfo(tuple(dirs), tuple(defines), resource_dir)
```

`backend/codetortoise/toolchain/libclang.py`:

```python
"""Loading libclang: vendor library if configured, else the one bundled with the `libclang` wheel."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

import clang.cindex as ci

_loaded: LibclangInfo | None = None


@dataclass(frozen=True)
class LibclangInfo:
    path: str
    version: str
    vendor: bool


def _version() -> str:
    fn = ci.conf.lib.clang_getClangVersion
    fn.restype = ci._CXString
    fn.errcheck = ci._CXString.from_result
    return fn()


def load_libclang(path: str | None) -> LibclangInfo:
    """Idempotent. Must be called before any other clang.cindex use in the process."""
    global _loaded
    if _loaded is not None:
        if path and _loaded.path != path:
            raise RuntimeError(f"libclang already loaded from {_loaded.path}, cannot switch to {path}")
        return _loaded
    if path:
        ci.Config.set_library_file(path)
    lib_path = path or ci.conf.get_filename()
    ctypes.CDLL(lib_path)  # fail early with a clear OSError if unloadable
    _loaded = LibclangInfo(path=lib_path, version=_version(), vendor=bool(path))
    return _loaded
```

`backend/codetortoise/toolchain/toolchain.py`:

```python
"""Toolchain: turns compile-DB entries into libclang args that work for the vendor cross toolchain."""
from __future__ import annotations

import os
from pathlib import Path

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.compile_db import CompileDb, sanitize_args
from codetortoise.toolchain.driver import DriverInfo, query_driver, target_flags
from codetortoise.toolchain.libclang import LibclangInfo, load_libclang

_CXX_EXTS = {".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx"}


def lang_of(path: str) -> str:
    return "c++" if Path(path).suffix.lower() in _CXX_EXTS else "c"


class Toolchain:
    def __init__(self, cfg: ToolchainConfig, cdb: CompileDb, work_dir: Path):
        self.cfg = cfg
        self.cdb = cdb
        self.work_dir = Path(work_dir)
        self.strip: set[str] = set(cfg.strip_flags)
        self.libclang: LibclangInfo | None = None
        self.driver: dict[str, DriverInfo] = {}
        self.driver_error: str | None = None
        self._preludes: dict[str, Path] = {}

    def prepare(self) -> None:
        """Idempotent: loads libclang and queries the driver once per process."""
        if self.libclang is not None:
            return
        self.libclang = load_libclang(self.cfg.libclang)
        if not self.cfg.clang or self.libclang.vendor or not self.cdb.entries:
            return
        self.work_dir.mkdir(parents=True, exist_ok=True)
        for lang in ("c", "c++"):
            sample = next((e for e in self.cdb.entries if lang_of(e.file) == lang), None)
            if sample is None:
                continue
            try:
                info = query_driver(self.cfg.clang, target_flags(sanitize_args(sample, self.strip)), lang)
            except RuntimeError as e:
                self.driver_error = str(e)
                continue
            self.driver[lang] = info
            prelude = self.work_dir / f"prelude-{'cxx' if lang == 'c++' else 'c'}.h"
            prelude.write_text("".join(f"#define {n} {v}\n" for n, v in info.defines))
            self._preludes[lang] = prelude

    def args_for(self, file: str) -> list[str]:
        entry = self.cdb.nearest_entry(file)
        if entry is None:
            return ["-x", "c++" if lang_of(file) == "c++" else "c"]
        args = sanitize_args(entry, self.strip)
        lang = lang_of(entry.file)
        info = self.driver.get(lang)
        if info is not None:
            rd = self.cfg.resource_dir or info.resource_dir
            if rd:
                args += ["-resource-dir", rd]
            for d in info.include_dirs:
                if rd and os.path.normpath(d).startswith(os.path.normpath(rd)):
                    continue
                args += ["-isystem", d]
            args += ["-include", str(self._preludes[lang]), "-Wno-macro-redefined",
                     "-Wno-builtin-macro-redefined"]
        return args
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_compile_db.py tests/test_driver_toolchain.py -q`
Expected: `8 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `30 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_compile_db.py backend/tests/test_driver_toolchain.py backend/codetortoise/toolchain/__init__.py backend/codetortoise/toolchain/compile_db.py backend/codetortoise/toolchain/driver.py backend/codetortoise/toolchain/libclang.py backend/codetortoise/toolchain/toolchain.py
git commit -m "feat(backend): compile DB, vendor driver query and libclang loading"
```

---

### Task 7: Repo-wide symbol index

A SQLite index of every C/C++ file under the workspace root, built with `cparse` (optionally in a
process pool). It answers the cheap, name-based questions that let a 5k+ TU codebase be scoped: who calls
function *name*, who references member *name*, who includes this header (directly or transitively), plus
resolved include and call edges between files for layer inference. The `generation` counter lets caches
(layers) invalidate on rebuild.

**Files:**
- Create: `backend/codetortoise/index/__init__.py`
- Create: `backend/codetortoise/index/symbols.py`
- Test: `backend/tests/test_symbols.py`

**Interfaces:**
- Consumes: `cparse`, `paths.canon`.
- Produces: `SymbolIndex(db_path)` with `build(root, workers=0) -> int`, `generation() -> int`, `files() -> list[str]`,
  `defs(name) -> list[DefRow]`, `callers_of(name) -> list[CallRow]`, `member_refs(field) -> list[MemberRow]`,
  `includers_of(header) -> list[str]`, `transitive_includers(header) -> set[str]`,
  `include_edges() -> list[tuple[str, str]]`, `call_edges_by_path() -> list[tuple[str, str]]`.
- `DefRow(qualname, path, line)`, `CallRow(caller|None, path, line)`, `MemberRow(fn|None, path, line, is_write)`;
  `iter_source_files(root) -> list[str]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_symbols.py`:

```python
import pytest

from codetortoise.index.symbols import SymbolIndex


@pytest.fixture(scope="module")
def index(fx, tmp_path_factory):
    idx = SymbolIndex(tmp_path_factory.mktemp("idx") / "symbols.db")
    assert idx.build(fx.root) == 9
    return idx


def rel(fx, paths):
    root = str(fx.root.resolve()) + "/"
    return sorted(p.replace(root, "") for p in paths)


def test_generation_increments(index):
    assert index.generation() >= 1


def test_callers_and_defs(index, fx):
    assert rel(fx, [r.path for r in index.callers_of("uart_send")]) == ["service/logger.c", "service/logger.c"]
    assert {r.caller for r in index.callers_of("uart_send")} == {"logger_write", "logger_flush"}
    assert [d.qualname for d in index.defs("hal_write")] == ["hal_write"]


def test_includers(index, fx):
    uart_h = str(fx.root / "driver/uart.h")
    assert rel(fx, index.includers_of(uart_h)) == ["driver/uart.c", "service/logger.h"]
    regs_h = str(fx.root / "include/hal/regs.h")
    assert rel(fx, index.transitive_includers(regs_h)) == [
        "app/main.c", "driver/uart.c", "driver/uart.h", "hal/regs.c", "service/logger.c", "service/logger.h"]


def test_member_refs(index):
    refs = index.member_refs("errors")
    assert {(r.fn, r.is_write) for r in refs} == {("uart_init", True), ("uart_errors", False)}


def test_edges(index, fx):
    inc = {(a.split("/")[-1], b.split("/")[-1]) for a, b in index.include_edges()}
    assert ("uart.c", "uart.h") in inc and ("uart.h", "regs.h") in inc
    calls = {(a.split("/")[-1], b.split("/")[-1]) for a, b in index.call_edges_by_path()}
    assert ("logger.c", "uart.c") in calls and ("uart.c", "regs.c") in calls
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_symbols.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.index'`

- [ ] **Step 3: Implement**

`backend/codetortoise/index/__init__.py` — empty file.

`backend/codetortoise/index/symbols.py`:

```python
"""Repo-wide tree-sitter symbol index stored in SQLite (heuristic, name-based)."""
from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from codetortoise.cparse import ParsedFile, is_source, parse_source
from codetortoise.paths import canon

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sym_meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sym_files(path TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sym_defs(name TEXT, qualname TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_calls(caller TEXT, callee TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_includes(path TEXT, inc TEXT, base TEXT);
CREATE TABLE IF NOT EXISTS sym_members(name TEXT, fn TEXT, path TEXT, line INTEGER, is_write INTEGER);
CREATE INDEX IF NOT EXISTS ix_defs_name ON sym_defs(name);
CREATE INDEX IF NOT EXISTS ix_calls_callee ON sym_calls(callee);
CREATE INDEX IF NOT EXISTS ix_inc_base ON sym_includes(base);
CREATE INDEX IF NOT EXISTS ix_members_name ON sym_members(name);
"""


@dataclass(frozen=True)
class DefRow:
    qualname: str
    path: str
    line: int


@dataclass(frozen=True)
class CallRow:
    caller: str | None
    path: str
    line: int


@dataclass(frozen=True)
class MemberRow:
    fn: str | None
    path: str
    line: int
    is_write: bool


def _parse_file(path: str) -> tuple[str, ParsedFile | None]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return path, parse_source(path, fh.read())
    except OSError:
        return path, None


def iter_source_files(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            p = os.path.join(dirpath, f)
            if is_source(p):
                out.append(canon(p))
    return sorted(out)


class SymbolIndex:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.executescript(_SCHEMA)

    def generation(self) -> int:
        row = self._db.execute("SELECT value FROM sym_meta WHERE key='generation'").fetchone()
        return int(row[0]) if row else 0

    def build(self, root: Path, workers: int = 0) -> int:
        """Full rebuild over every C/C++ source under root. Returns number of files indexed."""
        files = iter_source_files(Path(root))
        if workers and workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(_parse_file, files, chunksize=64))
        else:
            results = [_parse_file(f) for f in files]
        db = self._db
        with db:
            for t in ("sym_files", "sym_defs", "sym_calls", "sym_includes", "sym_members"):
                db.execute(f"DELETE FROM {t}")
            for path, pf in results:
                if pf is None:
                    continue
                db.execute("INSERT INTO sym_files VALUES(?)", (path,))
                db.executemany("INSERT INTO sym_defs VALUES(?,?,?,?)",
                               [(f.name, f.qualname, path, f.start_line) for f in pf.functions])
                db.executemany("INSERT INTO sym_calls VALUES(?,?,?,?)",
                               [(c.caller, c.callee, path, c.line) for c in pf.calls])
                db.executemany("INSERT INTO sym_includes VALUES(?,?,?)",
                               [(path, inc, os.path.basename(inc)) for inc in pf.includes])
                db.executemany("INSERT INTO sym_members VALUES(?,?,?,?,?)",
                               [(m.field, m.fn, path, m.line, int(m.is_write)) for m in pf.members])
            db.execute("INSERT OR REPLACE INTO sym_meta VALUES('generation', ?)", (str(self.generation() + 1),))
            db.execute("INSERT OR REPLACE INTO sym_meta VALUES('root', ?)", (str(root),))
        return sum(1 for _, pf in results if pf is not None)

    def files(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT path FROM sym_files ORDER BY path")]

    def defs(self, name: str) -> list[DefRow]:
        return [DefRow(*r) for r in self._db.execute(
            "SELECT qualname, path, line FROM sym_defs WHERE name=?", (name,))]

    def callers_of(self, name: str) -> list[CallRow]:
        return [CallRow(*r) for r in self._db.execute(
            "SELECT caller, path, line FROM sym_calls WHERE callee=?", (name,))]

    def member_refs(self, field_name: str) -> list[MemberRow]:
        return [MemberRow(r[0], r[1], r[2], bool(r[3])) for r in self._db.execute(
            "SELECT fn, path, line, is_write FROM sym_members WHERE name=?", (field_name,))]

    def includers_of(self, header: str) -> list[str]:
        header = canon(header)
        out = []
        for path, inc in self._db.execute(
                "SELECT path, inc FROM sym_includes WHERE base=?", (os.path.basename(header),)):
            inc_n = os.path.normpath(inc)
            if header == inc_n or header.endswith(os.sep + inc_n):
                out.append(path)
        return sorted(set(out))

    def transitive_includers(self, header: str, limit: int = 1_000_000) -> set[str]:
        seen: set[str] = set()
        frontier = [header]
        while frontier and len(seen) < limit:
            h = frontier.pop()
            for p in self.includers_of(h):
                if p not in seen:
                    seen.add(p)
                    frontier.append(p)
        return seen

    def include_edges(self) -> list[tuple[str, str]]:
        """Resolved (includer, included_file) pairs for files present in the index."""
        by_base: dict[str, list[str]] = {}
        for f in self.files():
            by_base.setdefault(os.path.basename(f), []).append(f)
        out = []
        for path, inc, base in self._db.execute("SELECT path, inc, base FROM sym_includes"):
            inc_n = os.path.normpath(inc)
            for cand in by_base.get(base, []):
                if cand == inc_n or cand.endswith(os.sep + inc_n):
                    out.append((path, cand))
        return out

    def call_edges_by_path(self) -> list[tuple[str, str]]:
        """(caller_path, callee_def_path) for callees with a unique definition."""
        rows = self._db.execute(
            "SELECT c.path, d.path FROM sym_calls c JOIN "
            "(SELECT name, MIN(path) AS path FROM sym_defs GROUP BY name HAVING COUNT(*) = 1) d "
            "ON d.name = c.callee")
        out = [(a, b) for a, b in rows]
        return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_symbols.py -q`
Expected: `5 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `35 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_symbols.py backend/codetortoise/index/__init__.py backend/codetortoise/index/symbols.py
git commit -m "feat(backend): repo-wide tree-sitter symbol index"
```

---

### Task 8: Facts model and alias-aware field access analysis (`aliasflow`)

The heart of "side effects not clearly identified". For one function cursor, `FunctionAnalyzer`:

1. collects local pointer/reference aliases to a fixpoint (`T *p = &s->f`, `T *p = s->child`, `auto &r = s.inner`,
   `p = &x`, pointer arithmetic, `?:`), each resolving to an access path rooted at a parameter, `this`, a global or a local;
2. records writes (`=`, compound assignment, `++/--`, `memcpy`/`memset` family first argument) and *may*-writes
   (passing an address or non-const reference to a callee), resolving through aliases, so `st->tx++` after
   `st = &u->stats` becomes a write to `u.stats.tx` with `via=["st"]`;
3. records reads of fields and globals.

Casts and pointer arithmetic lower confidence to `may` instead of being dropped. Passing a pointer *field's* pointee to a callee
(`consume(s->child)`) is not reported as a write to the field itself. Operator spellings come from tokens, because
the `libclang` 18 Python bindings have no `binary_operator` property.

**Files:**
- Create: `backend/codetortoise/facts/__init__.py`
- Create: `backend/codetortoise/facts/model.py`
- Create: `backend/codetortoise/facts/aliasflow.py`
- Test: `backend/tests/test_aliasflow.py`

**Interfaces:**
- Consumes: `toolchain.libclang.load_libclang` (tests).
- Produces `codetortoise.facts.model`: `Param`, `Function(usr, qualname, name, signature, return_type, params, file,
  start_line, end_line, is_virtual, method_key, is_static, returns)`, `CallEdge(caller, callee, callee_name, file, line,
  kind, result_used, compared, confidence)`, `FieldAccess(fn, field, field_name, record, path, root_kind, mode, via, file,
  line, confidence)`, `GlobalAccess(fn, var, var_name, mode, file, line)`, `TuInfo(file, variant, error_count, diagnostics,
  confidence, extractor)`, `Facts(tu, functions, calls, fields, globals)`; type aliases `Variant`, `Confidence`.
- Produces `codetortoise.facts.aliasflow`: `FunctionAnalyzer(fn_cursor, fn_usr).analyze() -> (list[FieldAccess], list[GlobalAccess])`,
  `AP` (access path), `operator_of(cursor) -> str`, `literal_text(cursor) -> str | None`, `_strip(cursor)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_aliasflow.py`:

```python
import clang.cindex as ci

from codetortoise.facts.aliasflow import FunctionAnalyzer
from codetortoise.toolchain.libclang import load_libclang

ALIAS_C = """struct Inner { int n; };
struct Foo { int count; struct Inner inner; struct Foo *child; int arr[4]; };
int helper(int *p);
void consume(struct Foo *f);
void *memset(void *s, int c, unsigned long n);
int g_total;
int touch(struct Foo *s, int v) {
  struct Foo *c = s->child;
  int *q = &s->count;
  struct Inner *in = &s->inner;
  int *e = s->arr + 2;
  struct Foo local;
  local.count = 1;
  c->count = v;
  *q += 1;
  in->n++;
  e[0] = 4;
  g_total = v;
  helper(&s->arr[1]);
  memset(&s->inner, 0, sizeof(s->inner));
  ((struct Inner *)q)->n = 2;
  consume(s->child);
  return 0;
}
"""

ALIAS_CPP = """struct Inner { int n; };
struct State { Inner inner; int x; };
struct Engine {
  int level;
  int step(State &st);
};
int Engine::step(State &st) {
  auto &r = st.inner;
  r.n += 2;
  level = 3;
  this->level++;
  State *p = nullptr;
  p = &st;
  p->x = 1;
  return 0;
}
"""


def writes(tmp_path, name, src, args, fn_name):
    load_libclang(None)
    f = tmp_path / name
    f.write_text(src)
    tu = ci.Index.create().parse(str(f), args=args)
    assert not [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    fn = next(c for c in tu.cursor.walk_preorder()
              if c.spelling == fn_name and c.is_definition() and c.kind in (ci.CursorKind.FUNCTION_DECL, ci.CursorKind.CXX_METHOD))
    fields, globs = FunctionAnalyzer(fn, fn.get_usr()).analyze()
    return fields, globs, {(a.line, a.path, a.mode, tuple(a.via), a.confidence) for a in fields if a.mode != "read"}


def test_c_alias_writes(tmp_path):
    fields, globs, w = writes(tmp_path, "alias.c", ALIAS_C, ["-xc"], "touch")
    assert (13, "local.count", "write", (), "precise") in w
    assert (14, "s.child->count", "write", ("c",), "precise") in w
    assert (15, "s.count", "write", ("q",), "precise") in w
    assert (16, "s.inner.n", "write", ("in",), "precise") in w
    assert (17, "s.arr[]", "write", ("e",), "may") in w
    assert (19, "s.arr[]", "may_write", ("call:helper",), "may") in w
    assert (20, "s.inner", "write", ("call:memset",), "precise") in w
    assert (21, "s.count.n", "write", ("q",), "may") in w
    # passing a pointer field's pointee on is not a write to the field itself
    assert not any(line == 22 for line, *_ in w)
    assert [(g.var_name, g.line) for g in globs if g.mode == "write"] == [("g_total", 18)]
    local = [a for a in fields if a.path == "local.count"][0]
    assert local.root_kind == "local"


def test_cpp_reference_this_and_reassigned_pointer(tmp_path):
    _, _, w = writes(tmp_path, "alias.cpp", ALIAS_CPP, ["-xc++", "-std=c++17"], "step")
    assert (9, "st.inner.n", "write", ("r",), "precise") in w
    assert (10, "this.level", "write", (), "precise") in w
    assert (11, "this.level", "write", (), "precise") in w
    assert (14, "st.x", "write", ("p",), "precise") in w


def test_reads_are_recorded_with_paths(tmp_path):
    fields, _, _ = writes(tmp_path, "alias.c", ALIAS_C, ["-xc"], "touch")
    reads = {(a.path, a.field_name) for a in fields if a.mode == "read"}
    assert ("s.child", "child") in reads
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_aliasflow.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.facts'`

- [ ] **Step 3: Implement**

`backend/codetortoise/facts/__init__.py` — empty file.

`backend/codetortoise/facts/model.py`:

```python
"""Language-agnostic facts emitted by FactExtractors."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Variant = Literal["before", "after"]
Confidence = Literal["precise", "may", "heuristic"]


class Param(BaseModel):
    name: str
    type: str
    is_const: bool = False


class Function(BaseModel):
    usr: str
    qualname: str
    name: str
    signature: str
    return_type: str
    params: list[Param] = Field(default_factory=list)
    file: str
    start_line: int
    end_line: int
    is_virtual: bool = False
    method_key: str | None = None
    is_static: bool = False
    returns: list[str] = Field(default_factory=list)


class CallEdge(BaseModel):
    caller: str
    callee: str
    callee_name: str
    file: str
    line: int
    kind: Literal["direct", "virtual"] = "direct"
    result_used: bool = True
    compared: list[str] = Field(default_factory=list)  # e.g. ["!=0", "==-1"]
    confidence: Confidence = "precise"


class FieldAccess(BaseModel):
    fn: str
    field: str            # FieldDecl USR, or "name:<field>" when heuristic
    field_name: str
    record: str
    path: str             # display access path, e.g. "u.stats.tx"
    root_kind: Literal["param", "this", "global", "local", "unknown"]
    mode: Literal["read", "write", "may_write"]
    via: list[str] = Field(default_factory=list)  # alias vars / calls involved
    file: str
    line: int
    confidence: Confidence = "precise"


class GlobalAccess(BaseModel):
    fn: str
    var: str
    var_name: str
    mode: Literal["read", "write"]
    file: str
    line: int


class TuInfo(BaseModel):
    file: str
    variant: Variant
    error_count: int = 0
    diagnostics: list[str] = Field(default_factory=list)
    confidence: Literal["precise", "degraded", "failed"] = "precise"
    extractor: Literal["clang", "treesitter"] = "clang"


class Facts(BaseModel):
    tu: TuInfo
    functions: list[Function] = Field(default_factory=list)
    calls: list[CallEdge] = Field(default_factory=list)
    fields: list[FieldAccess] = Field(default_factory=list)
    globals: list[GlobalAccess] = Field(default_factory=list)
```

`backend/codetortoise/facts/aliasflow.py`:

```python
"""Alias-aware field access analysis over a libclang function cursor.

Access paths are rooted at a parameter, `this`, a global, or a local. Local
pointer/reference variables are tracked as aliases of the object they point
to, so writes like `st->tx++` after `st = &u->stats` resolve to `u.stats.tx`.
Flow-insensitive within a function: aliases are collected to a fixpoint
first, then accesses are recorded.
"""
from __future__ import annotations

from dataclasses import dataclass

import clang.cindex as ci

from codetortoise.facts.model import FieldAccess, GlobalAccess

K = ci.CursorKind
T = ci.TypeKind

_WRAPPERS = {K.UNEXPOSED_EXPR, K.PAREN_EXPR}
_CASTS = {K.CSTYLE_CAST_EXPR, K.CXX_STATIC_CAST_EXPR, K.CXX_REINTERPRET_CAST_EXPR,
          K.CXX_CONST_CAST_EXPR, K.CXX_FUNCTIONAL_CAST_EXPR}
_PTR = {T.POINTER}
_REF = {T.LVALUEREFERENCE, T.RVALUEREFERENCE}
_ARRAY = {T.CONSTANTARRAY, T.INCOMPLETEARRAY, T.VARIABLEARRAY, T.DEPENDENTSIZEDARRAY}
_MEMFUNCS = {"memcpy", "memset", "memmove", "strcpy", "strncpy", "strcat", "strncat", "bzero"}
DEREF = ("*", "*", "")
ELEM = ("[]", "[]", "")
_FUNC_KINDS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.FUNCTION_TEMPLATE}


@dataclass(frozen=True)
class AP:
    """Access path: root plus field steps. steps: tuple of (field_usr, field_name, record) or ("[]","[]","")."""
    root_kind: str
    root: str
    steps: tuple[tuple[str, str, str], ...] = ()
    may: bool = False
    via: tuple[str, ...] = ()

    def plus(self, step: tuple[str, str, str], may: bool = False) -> AP:
        if step == ELEM and self.steps and self.steps[-1] == ELEM:
            return self.mark(may=may)
        return AP(self.root_kind, self.root, self.steps + (step,), self.may or may, self.via)

    def mark(self, may: bool = False, via: str | None = None) -> AP:
        return AP(self.root_kind, self.root, self.steps, self.may or may,
                  self.via + ((via,) if via and via not in self.via else ()))

    def display(self) -> str:
        out = self.root
        prev = ""
        for usr, name, _ in self.steps:
            if usr == "[]":
                out += "[]"
            elif usr == "*":
                out += "->"
            else:
                out += name if prev == "*" else "." + name
            prev = usr
        return out + ("*" if prev == "*" else "")

    def key(self) -> tuple:
        return (self.root_kind, self.root, self.steps)


def _strip(c: ci.Cursor) -> tuple[ci.Cursor, bool]:
    may = False
    while True:
        if c.kind in _WRAPPERS:
            kids = list(c.get_children())
            if len(kids) != 1:
                return c, may
            c = kids[0]
        elif c.kind in _CASTS:
            kids = [k for k in c.get_children() if k.kind.is_expression()]
            if not kids:
                return c, may
            c, may = kids[-1], True
        else:
            return c, may


def _type_kind(c: ci.Cursor) -> T:
    return c.type.get_canonical().kind


def operator_of(c: ci.Cursor) -> str:
    """Operator spelling for BINARY/COMPOUND/UNARY operator cursors (token based; works on any libclang)."""
    kids = list(c.get_children())
    toks = list(c.get_tokens())
    if c.kind in (K.BINARY_OPERATOR, K.COMPOUND_ASSIGNMENT_OPERATOR) and kids:
        lend = kids[0].extent.end.offset
        for tok in toks:
            if tok.extent.start.offset >= lend:
                return tok.spelling
        return ""
    if c.kind == K.UNARY_OPERATOR and kids and toks:
        if toks[0].extent.start.offset < kids[0].extent.start.offset:
            return "pre" + toks[0].spelling
        return "post" + toks[-1].spelling
    return ""


def literal_text(c: ci.Cursor) -> str | None:
    """Text of a literal-ish expression (int literal, -literal, enum constant, macro-expanded literal)."""
    s, _ = _strip(c)
    if s.kind in (K.INTEGER_LITERAL, K.CHARACTER_LITERAL, K.CXX_BOOL_LITERAL_EXPR, K.CXX_NULL_PTR_LITERAL_EXPR):
        toks = [t.spelling for t in s.get_tokens()]
        return "".join(toks) if toks else None
    if s.kind == K.UNARY_OPERATOR and operator_of(s) in ("pre-", "pre+"):
        kids = list(s.get_children())
        inner = literal_text(kids[0]) if kids else None
        return None if inner is None else operator_of(s)[3:] + inner
    if s.kind == K.DECL_REF_EXPR and s.referenced is not None and s.referenced.kind == K.ENUM_CONSTANT_DECL:
        return s.spelling
    return None


class FunctionAnalyzer:
    def __init__(self, fn: ci.Cursor, fn_usr: str):
        self.fn = fn
        self.fn_usr = fn_usr
        self.params: dict[str, tuple[int, ci.Cursor]] = {}
        for i, p in enumerate(fn.get_arguments() or []):
            self.params[p.get_usr()] = (i, p)
        self.alias: dict[str, set[AP]] = {}

    # ---- path resolution -------------------------------------------------
    def _var_root(self, ref: ci.Cursor) -> AP | None:
        usr = ref.get_usr()
        if usr in self.params:
            kind = ref.type.get_canonical().kind
            if kind in _PTR or kind in _REF:
                return AP("param", ref.spelling)
            return AP("local", ref.spelling)
        parent = ref.semantic_parent
        is_local = parent is not None and parent.kind in _FUNC_KINDS
        if not is_local or ref.storage_class == ci.StorageClass.STATIC:
            return AP("global", ref.spelling)
        return AP("local", ref.spelling)

    def lval(self, c: ci.Cursor) -> set[AP]:
        s, may = _strip(c)
        out: set[AP] = set()
        if s.kind == K.DECL_REF_EXPR and s.referenced is not None and s.referenced.kind in (K.VAR_DECL, K.PARM_DECL):
            ref = s.referenced
            usr = ref.get_usr()
            if ref.type.get_canonical().kind in _REF and usr in self.alias:
                out = {a.mark(via=ref.spelling) for a in self.alias[usr]}
            else:
                root = self._var_root(ref)
                if root is not None:
                    out = {root}
        elif s.kind == K.MEMBER_REF_EXPR and s.referenced is not None and s.referenced.kind == K.FIELD_DECL:
            f = s.referenced
            step = (f.get_usr(), f.spelling, f.semantic_parent.spelling if f.semantic_parent else "")
            kids = [k for k in s.get_children() if k.kind.is_expression()]
            if not kids:
                bases = {AP("this", "this")}
            else:
                b, _ = _strip(kids[0])
                if b.kind == K.CXX_THIS_EXPR:
                    bases = {AP("this", "this")}
                elif _type_kind(b) in _PTR:
                    bases = self.pointee(kids[0])
                else:
                    bases = self.lval(kids[0])
            out = {p.plus(step) for p in bases}
        elif s.kind == K.UNARY_OPERATOR and operator_of(s) == "pre*":
            kids = list(s.get_children())
            out = self.pointee(kids[0]) if kids else set()
        elif s.kind == K.ARRAY_SUBSCRIPT_EXPR:
            kids = list(s.get_children())
            if kids:
                base, _ = _strip(kids[0])
                src = self.lval(base) if _type_kind(base) in _ARRAY else self.pointee(kids[0])
                out = {p.plus(ELEM, may=False) for p in src}
        elif s.kind == K.CONDITIONAL_OPERATOR:
            kids = list(s.get_children())
            for k in kids[1:]:
                out |= self.lval(k)
            out = {a.mark(may=True) for a in out}
        return {a.mark(may=may) for a in out} if may else out

    def pointee(self, c: ci.Cursor) -> set[AP]:
        s, may = _strip(c)
        out: set[AP] = set()
        if _type_kind(s) in _ARRAY:
            out = {p.plus(ELEM) for p in self.lval(s)}
        elif s.kind == K.UNARY_OPERATOR and operator_of(s) == "pre&":
            kids = list(s.get_children())
            out = self.lval(kids[0]) if kids else set()
        elif s.kind == K.CXX_THIS_EXPR:
            out = {AP("this", "this")}
        elif s.kind == K.DECL_REF_EXPR and s.referenced is not None and s.referenced.kind in (K.VAR_DECL, K.PARM_DECL):
            ref = s.referenced
            usr = ref.get_usr()
            if usr in self.alias:
                out = {a.mark(via=ref.spelling) for a in self.alias[usr]}
            else:
                root = self._var_root(ref)
                if root is not None and root.root_kind in ("param", "global"):
                    out = {root}
        elif s.kind == K.MEMBER_REF_EXPR:
            out = {p.plus(DEREF) for p in self.lval(s)}
        elif s.kind == K.BINARY_OPERATOR and operator_of(s) in ("+", "-"):
            for k in s.get_children():
                kk, _ = _strip(k)
                if _type_kind(kk) in _PTR or _type_kind(kk) in _ARRAY:
                    out |= {p.plus(ELEM, may=True) for p in self.pointee(k)}
        elif s.kind == K.CONDITIONAL_OPERATOR:
            for k in list(s.get_children())[1:]:
                out |= self.pointee(k)
            out = {a.mark(may=True) for a in out}
        return {a.mark(may=may) for a in out} if may else out

    # ---- alias collection ------------------------------------------------
    def _alias_targets(self, var: ci.Cursor, init: ci.Cursor) -> set[AP]:
        kind = var.type.get_canonical().kind
        if kind in _PTR:
            return self.pointee(init)
        if kind in _REF:
            return self.lval(init)
        return set()

    def collect_aliases(self) -> None:
        for _ in range(4):
            changed = False
            for c in self.fn.walk_preorder():
                target_var, init = None, None
                if c.kind == K.VAR_DECL:
                    exprs = [k for k in c.get_children() if k.kind.is_expression()]
                    if exprs:
                        target_var, init = c, exprs[-1]
                elif c.kind == K.BINARY_OPERATOR and operator_of(c) == "=":
                    lhs, rhs = list(c.get_children())[:2]
                    l, _ = _strip(lhs)
                    if (l.kind == K.DECL_REF_EXPR and l.referenced is not None
                            and l.referenced.kind == K.VAR_DECL
                            and l.referenced.type.get_canonical().kind in _PTR):
                        target_var, init = l.referenced, rhs
                if target_var is None:
                    continue
                if self._var_root(target_var).root_kind == "global":
                    continue
                aps = self._alias_targets(target_var, init)
                if not aps:
                    continue
                cur = self.alias.setdefault(target_var.get_usr(), set())
                keys = {a.key() for a in cur}
                for a in aps:
                    if a.key() not in keys:
                        cur.add(a)
                        changed = True
            if not changed:
                return

    # ---- access recording ------------------------------------------------
    def analyze(self) -> tuple[list[FieldAccess], list[GlobalAccess]]:
        self.collect_aliases()
        fields: list[FieldAccess] = []
        globs: list[GlobalAccess] = []
        write_targets: set[int] = set()

        def emit(aps: set[AP], target: ci.Cursor, mode: str, extra_via: str | None = None) -> None:
            line = target.location.line
            file = target.location.file.name if target.location.file else ""
            emitted = False
            for a in aps:
                if a.steps and a.steps[-1] == DEREF and mode == "may_write":
                    emitted = True  # whole pointee object passed on; no specific field known
                    continue
                fstep = next((s for s in reversed(a.steps) if s[0] not in ("[]", "*")), None)
                if fstep is not None:
                    via = list(a.via) + ([extra_via] if extra_via else [])
                    fields.append(FieldAccess(
                        fn=self.fn_usr, field=fstep[0], field_name=fstep[1], record=fstep[2],
                        path=a.display(), root_kind=a.root_kind, mode=mode, via=via,
                        file=file, line=line, confidence="may" if (a.may or mode == "may_write") else "precise"))
                    emitted = True
                elif not a.steps and a.root_kind == "global" and mode != "may_write":
                    ref = _strip(target)[0].referenced
                    globs.append(GlobalAccess(fn=self.fn_usr, var=ref.get_usr() if ref else a.root,
                                              var_name=a.root, mode="write" if mode == "write" else "read",
                                              file=file, line=line))
            if not emitted and mode != "read":
                s, _ = _strip(target)
                if s.kind == K.MEMBER_REF_EXPR and s.referenced is not None and s.referenced.kind == K.FIELD_DECL:
                    f = s.referenced
                    fields.append(FieldAccess(
                        fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
                        record=f.semantic_parent.spelling if f.semantic_parent else "",
                        path="?." + f.spelling, root_kind="unknown", mode=mode,
                        via=[extra_via] if extra_via else [], file=file, line=line, confidence="may"))

        for c in self.fn.walk_preorder():
            k = c.kind
            if k == K.BINARY_OPERATOR and operator_of(c) == "=" or k == K.COMPOUND_ASSIGNMENT_OPERATOR:
                lhs = list(c.get_children())[0]
                write_targets.add(_strip(lhs)[0].hash)
                emit(self.lval(lhs), lhs, "write")
            elif k == K.UNARY_OPERATOR and operator_of(c)[-2:] in ("++", "--"):
                kids = list(c.get_children())
                if kids:
                    write_targets.add(_strip(kids[0])[0].hash)
                    emit(self.lval(kids[0]), kids[0], "write")
            elif k == K.CALL_EXPR and c.referenced is not None and c.referenced.kind in _FUNC_KINDS:
                callee = c.referenced
                args = list(c.get_arguments())
                if callee.spelling in _MEMFUNCS and args:
                    emit(self.pointee(args[0]), args[0], "write", extra_via=f"call:{callee.spelling}")
                    continue
                params = list(callee.get_arguments() or [])
                for i, arg in enumerate(args):
                    if i >= len(params):
                        break
                    pt = params[i].type.get_canonical()
                    if pt.kind in _PTR and not pt.get_pointee().is_const_qualified():
                        emit(self.pointee(arg), arg, "may_write", extra_via=f"call:{callee.spelling}")
                    elif pt.kind == T.LVALUEREFERENCE and not pt.get_pointee().is_const_qualified():
                        emit(self.lval(arg), arg, "may_write", extra_via=f"call:{callee.spelling}")
        for c in self.fn.walk_preorder():
            if c.kind == K.MEMBER_REF_EXPR and c.referenced is not None and c.referenced.kind == K.FIELD_DECL:
                if c.hash in write_targets:
                    continue
                aps = self.lval(c)
                f = c.referenced
                file = c.location.file.name if c.location.file else ""
                path = next(iter(sorted(a.display() for a in aps)), "?." + f.spelling)
                root = next(iter(sorted(a.root_kind for a in aps)), "unknown")
                fields.append(FieldAccess(
                    fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
                    record=f.semantic_parent.spelling if f.semantic_parent else "",
                    path=path, root_kind=root, mode="read", file=file, line=c.location.line,
                    confidence="precise" if aps else "may"))
            elif (c.kind == K.DECL_REF_EXPR and c.referenced is not None and c.referenced.kind == K.VAR_DECL
                  and c.hash not in write_targets):
                root = self._var_root(c.referenced)
                if root.root_kind == "global":
                    globs.append(GlobalAccess(fn=self.fn_usr, var=c.referenced.get_usr(), var_name=c.spelling,
                                              mode="read", file=c.location.file.name if c.location.file else "",
                                              line=c.location.line))
        return fields, globs
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_aliasflow.py -q`
Expected: `3 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `38 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_aliasflow.py backend/codetortoise/facts/__init__.py backend/codetortoise/facts/model.py backend/codetortoise/facts/aliasflow.py
git commit -m "feat(backend): alias-aware field access analysis on libclang cursors"
```

---

### Task 9: TU selection and inferred architectural layers

**TU selection** keeps clang work bounded: seeds are the changed TUs plus a sample of the TUs including
each changed header (total fan-out is recorded); callers found by name in the symbol index are added out to
`caller_hops`; TUs referencing members written by changed functions are added at hop 1; everything is ranked by
(hop, reference count) and cut at `tu_budget`.

**Layers** are inferred with zero config: files → modules (deepest directory whose subtree has ≥ `module_min_files`
sources), a module graph from include and uniquely-resolved call edges, strongly-connected components collapsed,
level = longest path to a sink (level 0 = lowest), bucketed down to `max_layers`.

**Files:**
- Create: `backend/codetortoise/tu_select.py`
- Create: `backend/codetortoise/layers.py`
- Test: `backend/tests/test_tu_select_layers.py`

**Interfaces:**
- Consumes: `diffmap.DiffMap`, `index.symbols.SymbolIndex`, `toolchain.compile_db.CompileDb`, `config.AnalysisConfig`.
- Produces: `TuSelection(selected: list[str], hops: dict[str, int], header_fanout: dict[str, int], over_budget: int)`,
  `select_tus(dm, index, cdb, cfg) -> TuSelection`.
- Produces: `Layer(level, name, description, modules)`, `LayerModel(root, generation, layers, module_level)` with
  `module_of(path)`, `level_of(path) -> int | None`, `layer(level) -> Layer | None`;
  `infer_layers(index, root, min_files=5, max_layers=8) -> LayerModel`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_tu_select_layers.py`:

```python
import os

import pytest

from codetortoise.config import AnalysisConfig
from codetortoise.diffmap import map_changes
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import infer_layers
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.tu_select import select_tus
from codetortoise.vcs.gitfixture import GitFixtureSource


@pytest.fixture(scope="module")
def index(fx, tmp_path_factory):
    idx = SymbolIndex(tmp_path_factory.mktemp("idx") / "s.db")
    idx.build(fx.root)
    return idx


def names(paths):
    return sorted(p.split("/")[-2] + "/" + p.split("/")[-1] for p in paths)


def test_selects_changed_tus_header_includers_and_callers(fx, fx_source, index):
    dm = map_changes(fx_source.load([101, 102]))
    sel = select_tus(dm, index, CompileDb.load(fx.compile_commands), AnalysisConfig())
    assert names(sel.selected) == ["app/main.c", "driver/uart.c", "hal/regs.c", "service/logger.c"]
    assert {k.split("/")[-1]: v for k, v in sel.header_fanout.items()} == {"uart.h": 3, "regs.h": 4}
    assert sel.over_budget == 0


def test_budget_caps_selection_changed_first(fx, fx_source, index):
    dm = map_changes(fx_source.load([101]))
    sel = select_tus(dm, index, CompileDb.load(fx.compile_commands), AnalysisConfig(tu_budget=1))
    assert names(sel.selected) == ["driver/uart.c"]
    assert sel.hops == {sel.selected[0]: 0}
    assert sel.over_budget == 2  # service/logger.c (hop 1) and app/main.c (hop 2) did not fit


def test_layers_from_dependency_graph(fx, index):
    lm = infer_layers(index, str(fx.root), min_files=1)
    assert lm.module_level == {"include/hal": 0, "cpp": 0, "hal": 1, "driver": 2, "service": 3, "app": 4}
    assert [l.name for l in lm.layers] == ["L0: cpp, include/hal", "L1: hal", "L2: driver", "L3: service", "L4: app"]
    assert lm.module_of(str(fx.root / "driver/new_file.c")) == "driver"
    assert lm.level_of(str(fx.root / "service/logger.c")) == 3


def test_layers_group_small_dirs_and_cap_count(fx, index):
    lm = infer_layers(index, str(fx.root), min_files=100)
    assert lm.module_level == {".": 0}
    lm = infer_layers(index, str(fx.root), min_files=1, max_layers=2)
    assert sorted(set(lm.module_level.values())) == [0, 1]


def test_symlinked_workspace_root_still_matches_compile_db(fx, tmp_path):
    link = tmp_path / "ws-link"
    os.symlink(fx.root, link)
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(link)
    dm = map_changes(GitFixtureSource(link).load([101]))
    sel = select_tus(dm, idx, CompileDb.load(fx.compile_commands), AnalysisConfig())
    assert names(sel.selected) == ["app/main.c", "driver/uart.c", "service/logger.c"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_tu_select_layers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.layers'`

- [ ] **Step 3: Implement**

`backend/codetortoise/tu_select.py`:

```python
"""Chooses which translation units get precise (clang) analysis, within a budget."""
from __future__ import annotations

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.cparse import is_header
from codetortoise.diffmap import DiffMap
from codetortoise.index.symbols import SymbolIndex
from codetortoise.toolchain.compile_db import CompileDb


class TuSelection(BaseModel):
    selected: list[str] = Field(default_factory=list)
    hops: dict[str, int] = Field(default_factory=dict)
    header_fanout: dict[str, int] = Field(default_factory=dict)
    over_budget: int = 0


def select_tus(dm: DiffMap, index: SymbolIndex, cdb: CompileDb, cfg: AnalysisConfig) -> TuSelection:
    tus = set(cdb.files())
    hop: dict[str, int] = {}
    refs: dict[str, int] = {}

    def add(path: str, h: int) -> None:
        if path not in tus:
            return
        hop[path] = min(hop.get(path, h), h)
        refs[path] = refs.get(path, 0) + 1

    sel = TuSelection()
    for f in dm.changed_files:
        if f in tus:
            add(f, 0)
        elif is_header(f):
            includers = index.transitive_includers(f)
            sel.header_fanout[f] = sum(1 for p in includers if p in tus)
            names = {c.name for c in dm.functions if c.file == f}
            names |= {t.name.split("::")[-1] for t in dm.types if t.file == f}
            users = {r.path for n in names for r in index.callers_of(n)}
            ranked = sorted((p for p in includers if p in tus), key=lambda p: (p not in users, p))
            for p in ranked[: cfg.header_sample_tus]:
                add(p, 0)

    frontier = {c.name for c in dm.functions}
    for h in range(1, cfg.caller_hops + 1):
        nxt: set[str] = set()
        for name in sorted(frontier):
            for row in index.callers_of(name):
                add(row.path, h)
                if row.caller:
                    nxt.add(row.caller.split("::")[-1])
        frontier = nxt - {c.name for c in dm.functions}
    for member in sorted({m for c in dm.functions for m in c.written_members}):
        for row in index.member_refs(member):
            add(row.path, 1)

    ranked = sorted(hop, key=lambda p: (hop[p], -refs[p], p))
    sel.selected = ranked[: cfg.tu_budget]
    sel.hops = {p: hop[p] for p in sel.selected}
    sel.over_budget = max(0, len(ranked) - cfg.tu_budget)
    return sel
```

`backend/codetortoise/layers.py`:

```python
"""Architectural layers inferred from the module dependency graph."""
from __future__ import annotations

import os
from collections import Counter

import networkx as nx
from pydantic import BaseModel, Field

from codetortoise.index.symbols import SymbolIndex
from codetortoise.paths import canon


class Layer(BaseModel):
    level: int
    name: str
    description: str = ""
    modules: list[str] = Field(default_factory=list)


class LayerModel(BaseModel):
    root: str
    generation: int = 0
    layers: list[Layer] = Field(default_factory=list)
    module_level: dict[str, int] = Field(default_factory=dict)

    def module_of(self, path: str) -> str:
        rel = os.path.relpath(os.path.dirname(canon(path)), self.root)
        rel = "." if rel in ("", ".") else rel
        cur = rel
        while True:
            if cur in self.module_level:
                return cur
            if cur in (".", "") or cur.startswith(".."):
                return "."
            cur = os.path.dirname(cur) or "."

    def level_of(self, path: str) -> int | None:
        return self.module_level.get(self.module_of(path))

    def layer(self, level: int | None) -> Layer | None:
        return next((l for l in self.layers if l.level == level), None)


def _modules(files: list[str], root: str, min_files: int) -> dict[str, str]:
    """file -> module dir (relative to root): deepest ancestor dir whose subtree has >= min_files files."""
    subtree: Counter[str] = Counter()
    rels = {}
    for f in files:
        d = os.path.relpath(os.path.dirname(f), root)
        rels[f] = d
        cur = d
        while True:
            subtree[cur] += 1
            if cur in (".", ""):
                break
            cur = os.path.dirname(cur) or "."
    out = {}
    for f, d in rels.items():
        cur = d
        while subtree[cur] < min_files and cur not in (".", ""):
            cur = os.path.dirname(cur) or "."
        out[f] = cur
    return out


def infer_layers(index: SymbolIndex, root: str, min_files: int = 5, max_layers: int = 8) -> LayerModel:
    root = canon(root)
    files = index.files()
    mod = _modules(files, root, min_files)
    g = nx.DiGraph()
    g.add_nodes_from(set(mod.values()))
    for a, b in index.include_edges() + index.call_edges_by_path():
        ma, mb = mod.get(a), mod.get(b)
        if ma and mb and ma != mb:
            g.add_edge(ma, mb)
    cond = nx.condensation(g)
    level: dict[int, int] = {}
    for n in reversed(list(nx.topological_sort(cond))):
        succ = list(cond.successors(n))
        level[n] = 0 if not succ else 1 + max(level[s] for s in succ)
    top = max(level.values(), default=0)
    if top + 1 > max_layers:
        level = {n: l * max_layers // (top + 1) for n, l in level.items()}
    module_level = {m: level[cond.graph["mapping"][m]] for m in g.nodes}
    layers = []
    for lv in sorted(set(module_level.values())):
        mods = sorted(m for m, l in module_level.items() if l == lv)
        layers.append(Layer(level=lv, name=f"L{lv}: {', '.join(mods[:3])}", modules=mods))
    return LayerModel(root=root, generation=index.generation(), layers=layers, module_level=module_level)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_tu_select_layers.py -q`
Expected: `5 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `43 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_tu_select_layers.py backend/codetortoise/tu_select.py backend/codetortoise/layers.py
git commit -m "feat(backend): budgeted TU selection and graph-inferred layers"
```

---

### Task 10: Clang fact extractor, tree-sitter fallback, extraction runner

`extract_tu` parses one TU (with changed files supplied as libclang *unsaved files*, which is how the
"before" and "after" variants are analysed without touching the workspace) and emits facts for functions
defined in the TU's main file or any changed file: signatures, literal return values, calls (virtual or direct,
whether the result is used, and what literals it is compared against), and `aliasflow` field/global accesses.
Unknown vendor flags reported by libclang are stripped and the parse is retried once. Parse errors lower
confidence to `degraded`; if clang cannot produce a TU at all (or raises), the runner falls back to the
tree-sitter extractor (heuristic facts). `run_extraction` fans out over a process pool.

**Files:**
- Create: `backend/codetortoise/facts/clang_extractor.py`
- Create: `backend/codetortoise/facts/treesitter_extractor.py`
- Create: `backend/codetortoise/facts/runner.py`
- Test: `backend/tests/test_clang_extractor.py`
- Test: `backend/tests/test_runner.py`

**Interfaces:**
- Consumes: `facts.aliasflow`, `facts.model`, `cparse`, `toolchain.Toolchain`, `tu_select.TuSelection`, `vcs.model.ChangeSet`.
- Produces: `TuRequest(file, args, variant, unsaved: dict[str, str], focus: list[str])`, `extract_tu(req) -> Facts`,
  `qualname_of(cursor)`, `function_fact(cursor) -> Function`.
- Produces: `extract_tu_treesitter(req, reason="") -> Facts` (usr `ts:<file>#<qualname>`, callee `name:<callee>`).
- Produces: `build_requests(sel, cs, tc, variant) -> list[TuRequest]`,
  `run_extraction(reqs, libclang_path, workers, progress=None) -> list[Facts]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_clang_extractor.py`:

```python
from codetortoise.facts.clang_extractor import TuRequest, extract_tu


def args(fx, lang="c"):
    base = ["-xc"] if lang == "c" else ["-xc++", "-std=c++17"]
    return base + [f"-I{fx.root}/include", f"-I{fx.root}"]


def test_after_variant_uses_unsaved_content(fx, fx_source):
    cs = fx_source.load([101])
    uart = cs.files[0]
    before = extract_tu(TuRequest(file=uart.local, args=args(fx), variant="before"))
    after = extract_tu(TuRequest(file=uart.local, args=args(fx), variant="after", unsaved={uart.local: uart.after}))
    fb = {f.qualname: f for f in before.functions}
    fa = {f.qualname: f for f in after.functions}
    assert fb["uart_send"].returns == ["0"]
    assert fa["uart_send"].returns == ["-2", "0"]
    assert fa["uart_send"].signature == "int uart_send(struct Uart *, const char *, int)"
    assert [p.is_const for p in fa["uart_send"].params] == [False, True, False]
    assert after.tu.confidence == "precise"


def test_call_result_usage(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "service/logger.c"), args=args(fx), variant="before"))
    calls = {(c.callee_name, c.line): c for c in facts.calls}
    assert calls[("uart_send", 12)].result_used and calls[("uart_send", 12)].compared == ["!=0"]
    assert not calls[("uart_send", 21)].result_used


def test_virtual_calls_and_methods(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "cpp/engine.cpp"), args=args(fx, "c++"), variant="before"))
    fns = {f.qualname: f for f in facts.functions}
    assert fns["svc::Engine::base"].is_virtual and fns["svc::Engine::base"].method_key == "base#&$@S@State#"
    assert not fns["svc::Engine::step"].is_virtual
    (call,) = [c for c in facts.calls if c.callee_name == "svc::Engine::base"]
    assert call.kind == "virtual"


def test_unknown_vendor_flags_are_stripped_and_retried(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "hal/regs.c"),
                                 args=args(fx) + ["-mvendor-special", "--vendor-opt=2"], variant="before"))
    assert facts.tu.confidence == "precise" and facts.tu.error_count == 0
    assert {f.qualname for f in facts.functions} == {"hal_read", "hal_write"}


def test_parse_errors_degrade_confidence(tmp_path):
    f = tmp_path / "bad.c"
    f.write_text("#include \"missing.h\"\nint ok(void) { return 1; }\n")
    facts = extract_tu(TuRequest(file=str(f), args=["-xc"], variant="before"))
    assert facts.tu.confidence == "degraded" and facts.tu.error_count == 1
    assert [fn.qualname for fn in facts.functions] == ["ok"]
```

`backend/tests/test_runner.py`:

```python
from codetortoise.config import ToolchainConfig
from codetortoise.facts import runner
from codetortoise.facts.clang_extractor import TuRequest
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import TuSelection
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def test_build_requests_handles_added_and_deleted_files(fx, tmp_path):
    root = str(fx.root.resolve())
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/driver/uart.c", local=f"{root}/driver/uart.c", action="edit", before="B", after="A"),
        FileChange(depot="//d/driver/new.c", local=f"{root}/driver/new.c", action="add", before="", after="N"),
        FileChange(depot="//d/app/main.c", local=f"{root}/app/main.c", action="delete", before="M", after="")])
    tc = Toolchain(ToolchainConfig(), CompileDb.load(fx.compile_commands), tmp_path)
    sel = TuSelection(selected=[f"{root}/driver/uart.c", f"{root}/app/main.c"])
    before = runner.build_requests(sel, cs, tc, "before")
    after = runner.build_requests(sel, cs, tc, "after")
    assert [r.file.split("/")[-1] for r in before] == ["uart.c", "main.c"]
    assert [r.file.split("/")[-1] for r in after] == ["uart.c", "new.c"]
    assert before[0].unsaved == {f"{root}/driver/uart.c": "B", f"{root}/app/main.c": "M"}
    assert after[0].unsaved == {f"{root}/driver/uart.c": "A", f"{root}/driver/new.c": "N"}
    assert "-I" + root + "/include" in after[1].args  # new file borrows args from its directory neighbour


def test_falls_back_to_treesitter_when_clang_raises(monkeypatch, tmp_path):
    f = tmp_path / "x.c"
    f.write_text("int f(struct S *s) { s->a = 1; return g(); }\n")

    def boom(req):
        raise RuntimeError("libclang crashed")

    monkeypatch.setattr(runner, "extract_tu", boom)
    (facts,) = runner.run_extraction([TuRequest(file=str(f), args=[], variant="after")], None, workers=1)
    assert facts.tu.extractor == "treesitter" and facts.tu.confidence == "failed"
    assert [fn.qualname for fn in facts.functions] == ["f"]
    assert [(c.callee, c.confidence) for c in facts.calls] == [("name:g", "heuristic")]
    assert [(a.field_name, a.mode) for a in facts.fields] == [("a", "write")]


def test_process_pool_extraction(fx, tmp_path):
    tc = Toolchain(ToolchainConfig(), CompileDb.load(fx.compile_commands), tmp_path)
    files = [str(fx.root / "hal/regs.c"), str(fx.root / "driver/uart.c")]
    reqs = [TuRequest(file=f, args=tc.args_for(f), variant="before") for f in files]
    out = runner.run_extraction(reqs, None, workers=2)
    assert [len(f.functions) for f in out] == [2, 3]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_clang_extractor.py tests/test_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.facts.clang_extractor'`

- [ ] **Step 3: Implement**

`backend/codetortoise/facts/clang_extractor.py`:

```python
"""libclang-based FactExtractor. Designed to run inside worker processes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import clang.cindex as ci

from codetortoise.facts.aliasflow import (
    FunctionAnalyzer,
    _strip,
    literal_text,
    operator_of,
)
from codetortoise.facts.model import CallEdge, Facts, Function, Param, TuInfo
from codetortoise.paths import canon

K = ci.CursorKind
_FUNC_KINDS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.FUNCTION_TEMPLATE}
_SCOPE_KINDS = {K.NAMESPACE, K.CLASS_DECL, K.STRUCT_DECL, K.UNION_DECL, K.CLASS_TEMPLATE}
_UNKNOWN_ARG = re.compile(r"unknown argument:? '([^']+)'")
_CMP_OPS = {"==", "!=", "<", ">", "<=", ">="}


@dataclass
class TuRequest:
    file: str
    args: list[str]
    variant: str
    unsaved: dict[str, str] = field(default_factory=dict)
    focus: list[str] = field(default_factory=list)


def _norm(path: str) -> str:
    return canon(path)


def qualname_of(c: ci.Cursor) -> str:
    parts = [c.spelling]
    p = c.semantic_parent
    while p is not None and p.kind in _SCOPE_KINDS:
        if p.spelling:
            parts.append(p.spelling)
        p = p.semantic_parent
    return "::".join(reversed(parts))


def _param(p: ci.Cursor) -> Param:
    t = p.type.get_canonical()
    if t.kind in (ci.TypeKind.POINTER, ci.TypeKind.LVALUEREFERENCE, ci.TypeKind.RVALUEREFERENCE):
        is_const = t.get_pointee().is_const_qualified()
    else:
        is_const = t.is_const_qualified()
    return Param(name=p.spelling, type=p.type.spelling, is_const=is_const)


def function_fact(c: ci.Cursor) -> Function:
    params = [_param(p) for p in (c.get_arguments() or [])]
    qual = qualname_of(c)
    rt = c.result_type.spelling if c.kind not in (K.CONSTRUCTOR, K.DESTRUCTOR) else ""
    sig = f"{rt} {qual}({', '.join(p.type for p in params)})".strip()
    if c.kind == K.CXX_METHOD and c.is_const_method():
        sig += " const"
    is_virtual = c.kind == K.CXX_METHOD and c.is_virtual_method()
    usr = c.get_usr()
    returns: list[str] = []
    for r in c.walk_preorder():
        if r.kind == K.RETURN_STMT:
            kids = list(r.get_children())
            if kids:
                lit = literal_text(kids[0])
                if lit is not None and lit not in returns:
                    returns.append(lit)
    return Function(
        usr=usr, qualname=qual, name=c.spelling, signature=sig, return_type=rt, params=params,
        file=_norm(c.location.file.name), start_line=c.extent.start.line, end_line=c.extent.end.line,
        is_virtual=is_virtual, method_key=usr.split("@F@", 1)[-1] if is_virtual else None,
        is_static=c.storage_class == ci.StorageClass.STATIC, returns=returns)


_WRAP = {K.UNEXPOSED_EXPR, K.PAREN_EXPR}
_STMT_PARENTS = {K.COMPOUND_STMT, K.CASE_STMT, K.DEFAULT_STMT, K.LABEL_STMT}


def _result_unused(parent: ci.Cursor | None, idx: int, n: int) -> bool:
    if parent is None:
        return False
    k = parent.kind
    if k in _STMT_PARENTS:
        return True
    if k == K.IF_STMT:
        return idx >= 1
    if k in (K.FOR_STMT, K.WHILE_STMT):
        return idx == n - 1
    if k == K.DO_STMT:
        return idx == 0
    if k == K.CSTYLE_CAST_EXPR:
        return parent.type.spelling == "void"
    return False


def _calls(fn: ci.Cursor, fn_usr: str) -> list[CallEdge]:
    out: list[CallEdge] = []

    def visit(c: ci.Cursor, parent: ci.Cursor | None, idx: int, n: int) -> None:
        if (c.kind == K.CALL_EXPR and c.referenced is not None and c.referenced.kind in _FUNC_KINDS
                and c.referenced.kind != K.CONSTRUCTOR):
            callee = c.referenced
            kids = list(c.get_children())
            via_member = bool(kids) and _strip(kids[0])[0].kind == K.MEMBER_REF_EXPR
            is_virtual = callee.kind == K.CXX_METHOD and callee.is_virtual_method() and via_member
            compared: list[str] = []
            if parent is not None and parent.kind == K.BINARY_OPERATOR:
                op = operator_of(parent)
                if op in _CMP_OPS:
                    for other in parent.get_children():
                        lit = literal_text(other)
                        if lit is not None:
                            compared.append(f"{op}{lit}")
            out.append(CallEdge(
                caller=fn_usr, callee=callee.get_usr(), callee_name=qualname_of(callee),
                file=_norm(c.location.file.name) if c.location.file else "", line=c.location.line,
                kind="virtual" if is_virtual else "direct",
                result_used=not _result_unused(parent, idx, n), compared=compared))
        kids = list(c.get_children())
        for i, ch in enumerate(kids):
            if c.kind in _WRAP:
                visit(ch, parent, idx, n)
            else:
                visit(ch, c, i, len(kids))

    visit(fn, None, 0, 1)
    return out


def _parse(index: ci.Index, req: TuRequest, args: list[str]) -> ci.TranslationUnit:
    unsaved = [(p, t) for p, t in req.unsaved.items()]
    return index.parse(req.file, args=args, unsaved_files=unsaved, options=ci.TranslationUnit.PARSE_INCOMPLETE)


def extract_tu(req: TuRequest) -> Facts:
    """Parse one TU and emit facts for functions defined in the main file or any focus file."""
    index = ci.Index.create()
    args = list(req.args)
    try:
        tu = _parse(index, req, args)
        bad = [m.group(1) for d in tu.diagnostics if (m := _UNKNOWN_ARG.search(d.spelling))]
        if bad:
            args = [a for a in args if a not in bad and a.split("=", 1)[0] not in bad]
            tu = _parse(index, req, args)
    except ci.TranslationUnitLoadError as e:
        return Facts(tu=TuInfo(file=_norm(req.file), variant=req.variant, confidence="failed",
                               diagnostics=[str(e)]))
    errors = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    info = TuInfo(file=_norm(req.file), variant=req.variant, error_count=len(errors),
                  diagnostics=[f"{d.location.file}:{d.location.line}: {d.spelling}" for d in errors[:20]],
                  confidence="precise" if not errors else "degraded")
    focus = {_norm(f) for f in req.focus} | {_norm(req.file)}
    facts = Facts(tu=info)
    seen: set[str] = set()
    for c in tu.cursor.walk_preorder():
        if c.kind not in _FUNC_KINDS or not c.is_definition() or c.location.file is None:
            continue
        if _norm(c.location.file.name) not in focus:
            continue
        usr = c.get_usr()
        if usr in seen:
            continue
        seen.add(usr)
        facts.functions.append(function_fact(c))
        facts.calls.extend(_calls(c, usr))
        fa, ga = FunctionAnalyzer(c, usr).analyze()
        facts.fields.extend(fa)
        facts.globals.extend(ga)
    return facts
```

`backend/codetortoise/facts/treesitter_extractor.py`:

```python
"""Heuristic FactExtractor used when clang cannot parse a TU."""
from __future__ import annotations

from pathlib import Path

from codetortoise.cparse import parse_source
from codetortoise.facts.clang_extractor import TuRequest, _norm
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo


def extract_tu_treesitter(req: TuRequest, reason: str = "") -> Facts:
    file = _norm(req.file)
    text = req.unsaved.get(req.file)
    if text is None:
        p = Path(req.file)
        text = p.read_text(errors="replace") if p.exists() else ""
    pf = parse_source(file, text)

    def usr(q: str) -> str:
        return f"ts:{file}#{q}"

    facts = Facts(tu=TuInfo(file=file, variant=req.variant, confidence="failed", extractor="treesitter",
                            diagnostics=[reason] if reason else []))
    for f in pf.functions:
        facts.functions.append(Function(usr=usr(f.qualname), qualname=f.qualname, name=f.name,
                                        signature=f.signature, return_type="", file=file,
                                        start_line=f.start_line, end_line=f.end_line))
    for c in pf.calls:
        if c.caller:
            facts.calls.append(CallEdge(caller=usr(c.caller), callee=f"name:{c.callee}", callee_name=c.callee,
                                        file=file, line=c.line, confidence="heuristic"))
    for m in pf.members:
        if m.fn:
            facts.fields.append(FieldAccess(fn=usr(m.fn), field=f"name:{m.field}", field_name=m.field, record="",
                                            path=f"?.{m.field}", root_kind="unknown",
                                            mode="write" if m.is_write else "read", file=file, line=m.line,
                                            confidence="heuristic"))
    return facts
```

`backend/codetortoise/facts/runner.py`:

```python
"""Builds TU requests for a change set and runs extraction (optionally in a process pool)."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

from codetortoise.cparse import is_header
from codetortoise.facts.clang_extractor import TuRequest, extract_tu
from codetortoise.facts.model import Facts
from codetortoise.facts.treesitter_extractor import extract_tu_treesitter
from codetortoise.toolchain.libclang import load_libclang
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import TuSelection
from codetortoise.vcs.model import ChangeSet


def build_requests(sel: TuSelection, cs: ChangeSet, tc: Toolchain, variant: str) -> list[TuRequest]:
    unsaved: dict[str, str] = {}
    for f in cs.files:
        if variant == "before" and f.action != "add":
            unsaved[f.local] = f.before
        elif variant == "after" and f.action != "delete":
            unsaved[f.local] = f.after
    focus = [f.local for f in cs.files]
    tus = list(sel.selected)
    for f in cs.files:  # new source files are TUs only in "after"; deleted ones only in "before"
        if is_header(f.local) or f.local in tus:
            continue
        if (variant == "after" and f.action == "add") or (variant == "before" and f.action == "delete"):
            tus.append(f.local)
    reqs = []
    for tu in tus:
        if variant == "after" and any(f.local == tu and f.action == "delete" for f in cs.files):
            continue
        if variant == "before" and any(f.local == tu and f.action == "add" for f in cs.files):
            continue
        reqs.append(TuRequest(file=tu, args=tc.args_for(tu), variant=variant, unsaved=unsaved, focus=focus))
    return reqs


def _extract_with_fallback(req: TuRequest) -> Facts:
    try:
        facts = extract_tu(req)
    except Exception as e:  # libclang crash paths surface as Python exceptions
        return extract_tu_treesitter(req, reason=f"clang extractor error: {e}")
    if facts.tu.confidence == "failed":
        return extract_tu_treesitter(req, reason="; ".join(facts.tu.diagnostics))
    return facts


def run_extraction(reqs: list[TuRequest], libclang_path: str | None, workers: int,
                   progress: Callable[[int, int], None] | None = None) -> list[Facts]:
    out: list[Facts] = []
    if workers <= 1 or len(reqs) <= 1:
        load_libclang(libclang_path)
        for i, r in enumerate(reqs):
            out.append(_extract_with_fallback(r))
            if progress:
                progress(i + 1, len(reqs))
        return out
    with ProcessPoolExecutor(max_workers=workers, initializer=load_libclang, initargs=(libclang_path,)) as pool:
        for i, facts in enumerate(pool.map(_extract_with_fallback, reqs)):
            out.append(facts)
            if progress:
                progress(i + 1, len(reqs))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_clang_extractor.py tests/test_runner.py -q`
Expected: `8 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `51 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_clang_extractor.py backend/tests/test_runner.py backend/codetortoise/facts/clang_extractor.py backend/codetortoise/facts/treesitter_extractor.py backend/codetortoise/facts/runner.py
git commit -m "feat(backend): clang fact extractor with vendor-flag retry and tree-sitter fallback"
```

---

### Task 11: Impact model: call flows, blast radius, header fan-out

Merges before/after facts into one graph whose nodes are functions (by USR) and fields (by FieldDecl
USR), with `call`/`virtual`/`writes`/`reads` edges carrying `added | removed | unchanged` status and
`precise | may | heuristic` confidence. Virtual calls fan out to every override sharing the method key. Callers and
member references outside the parsed TUs come from the symbol index as heuristic edges.

- **Flows:** per changed function, callees to `flow_depth` plus callers to `caller_hops`.
- **Blast radius:** reverse call reachability from the changed functions, plus data coupling (anyone reading/writing a
  field a changed function writes). Score = Σ confidence/hop, ×1.5 for cross-layer callers, ×1.5 for entry points,
  ×1.3 via virtual dispatch.
- **Fan-out:** TUs including each changed header, by layer.

`tests/conftest.py` gains the session-scoped `analysed` fixture (CLs 101+102 run through the whole analysis) reused by later tests.

**Files:**
- Create: `backend/codetortoise/impact.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_impact.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `Node(id, key, kind, label, file, line, status, layer, confidence)`, `Edge(id, src, dst, kind, status, confidence,
  file, line)`, `Flow(root, nodes, edges)`, `BlastItem(node, hop, score, via, path)`, `FanOut(header, total_tus, by_layer)`,
  `ImpactModel(nodes: dict[str, Node], edges, changed, flows, blast, fanout)` with `node_by_key(key)`,
  `edges_into(node_id, kinds)`; `build_impact(before, after, dm, sel, index, layers, cfg) -> ImpactModel`.
- Node ids are `N1..`, edge ids `E1..`, assigned in sorted key order (stable for a given input).
- Produces test fixture `analysed` → `SimpleNamespace(cfg, cs, dm, sel, layers, before, after, impact)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/conftest.py` (replace the whole file):

```python
from types import SimpleNamespace

import pytest

from codetortoise.config import AnalysisConfig, ToolchainConfig
from codetortoise.diffmap import map_changes
from codetortoise.facts.runner import build_requests, run_extraction
from codetortoise.fixture import build_fixture
from codetortoise.impact import build_impact
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import infer_layers
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import select_tus
from codetortoise.vcs.gitfixture import GitFixtureSource


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """Git-backed fixture workspace checked out at the base commit (CLs 101 and 102 exist as commits)."""
    return build_fixture(tmp_path_factory.mktemp("fixture"))


@pytest.fixture(scope="session")
def fx_source(fx):
    return GitFixtureSource(fx.root)


@pytest.fixture(scope="session")
def analysed(fx, fx_source, tmp_path_factory):
    """CLs 101+102 run through diffmap, TU selection, clang facts and the impact model."""
    tmp = tmp_path_factory.mktemp("impact")
    cfg = AnalysisConfig(module_min_files=1)
    cs = fx_source.load([101, 102])
    dm = map_changes(cs)
    idx = SymbolIndex(tmp / "s.db")
    idx.build(fx.root)
    cdb = CompileDb.load(fx.compile_commands)
    tc = Toolchain(ToolchainConfig(), cdb, tmp / "tc")
    tc.prepare()
    sel = select_tus(dm, idx, cdb, cfg)
    layers = infer_layers(idx, str(fx.root), 1)
    before = run_extraction(build_requests(sel, cs, tc, "before"), None, 1)
    after = run_extraction(build_requests(sel, cs, tc, "after"), None, 1)
    im = build_impact(before, after, dm, sel, idx, layers, cfg)
    return SimpleNamespace(cfg=cfg, cs=cs, dm=dm, sel=sel, layers=layers, before=before, after=after, impact=im)
```

`backend/tests/test_impact.py`:

```python
def by_label(im):
    return {n.label: n for n in im.nodes.values()}


def test_changed_nodes_and_layers(analysed):
    im = analysed.impact
    nodes = by_label(im)
    assert sorted(im.nodes[n].label for n in im.changed) == ["hal_write", "uart_send"]
    assert nodes["uart_send"].status == "changed" and nodes["uart_send"].layer == 2
    assert nodes["main"].layer == 4 and nodes["Stats::tx"].kind == "field"


def test_new_data_edges_are_added(analysed):
    im = analysed.impact
    nodes = by_label(im)
    edges = {(im.nodes[e.src].label, e.kind, im.nodes[e.dst].label): e for e in im.edges}
    assert edges[("uart_send", "writes", "Stats::tx")].status == "added"
    assert edges[("uart_send", "writes", "Uart::errors")].status == "added"
    assert edges[("logger_flush", "call", "uart_send")].status == "unchanged"
    assert ("logger_write", "writes", "Logger::uart") not in edges  # passing lg->uart on is not a field write
    flow = next(f for f in im.flows if f.root == nodes["uart_send"].id)
    assert [im.nodes[n].label for n in flow.nodes] == ["uart_send", "hal_write", "logger_flush", "logger_write", "main"]


def test_blast_radius_call_and_data(analysed):
    im = analysed.impact
    blast = {im.nodes[b.node].label: b for b in im.blast}
    assert blast["logger_flush"].hop == 1 and blast["logger_flush"].via == "call"
    assert blast["uart_errors"].via == "data"  # reads Uart::errors, newly written by uart_send
    assert blast["main"].hop == 2
    assert blast["uart_init"].score > blast["logger_flush"].score  # main is an entry point two layers up
    assert [im.nodes[p].label for p in blast["main"].path] == ["main", "uart_init", "hal_write"]


def test_header_fanout_counts_tus_by_layer(analysed):
    im = analysed.impact
    fan = {f.header.split("/")[-1]: f for f in im.fanout}
    assert fan["uart.h"].total_tus == 3
    assert fan["uart.h"].by_layer == {"L2: driver": 1, "L3: service": 1, "L4: app": 1}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_impact.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.impact'`

- [ ] **Step 3: Implement**

`backend/codetortoise/impact.py`:

```python
"""Impact model: before/after call + data-coupling graph, call flows, blast radius, header fan-out."""
from __future__ import annotations

import fnmatch
from collections import deque
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.cparse import is_header
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts, Function
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import LayerModel
from codetortoise.tu_select import TuSelection

Status = Literal["added", "removed", "changed", "unchanged"]
EdgeKind = Literal["call", "virtual", "writes", "reads"]
EdgeConf = Literal["precise", "may", "heuristic"]
_WEIGHT = {"precise": 1.0, "may": 0.6, "heuristic": 0.4}


class Node(BaseModel):
    id: str
    key: str
    kind: Literal["function", "field"] = "function"
    label: str
    file: str | None = None
    line: int | None = None
    status: Status = "unchanged"
    layer: int | None = None
    confidence: Literal["precise", "heuristic"] = "precise"


class Edge(BaseModel):
    id: str
    src: str
    dst: str
    kind: EdgeKind
    status: Literal["added", "removed", "unchanged"] = "unchanged"
    confidence: EdgeConf = "precise"
    file: str | None = None
    line: int | None = None


class Flow(BaseModel):
    root: str
    nodes: list[str]
    edges: list[str]


class BlastItem(BaseModel):
    node: str
    hop: int
    score: float
    via: Literal["call", "data"]
    path: list[str]


class FanOut(BaseModel):
    header: str
    total_tus: int
    by_layer: dict[str, int] = Field(default_factory=dict)


class ImpactModel(BaseModel):
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    blast: list[BlastItem] = Field(default_factory=list)
    fanout: list[FanOut] = Field(default_factory=list)

    def node_by_key(self, key: str) -> Node | None:
        return next((n for n in self.nodes.values() if n.key == key), None)

    def edges_into(self, node_id: str, kinds: set[str]) -> list[Edge]:
        return [e for e in self.edges if e.dst == node_id and e.kind in kinds]


def _overlaps(fn: Function, file: str, lines: tuple[int, int] | None) -> bool:
    return (lines is not None and fn.file == file
            and fn.start_line <= lines[1] and lines[0] <= fn.end_line)


class _Builder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}                 # key -> node attrs
        self.edges: dict[tuple, dict] = {}               # (src_key, dst_key, kind) -> attrs

    def node(self, key: str, **attrs) -> None:
        cur = self.nodes.setdefault(key, {"key": key})
        for k, v in attrs.items():
            if v is not None and (k not in cur or cur[k] is None):
                cur[k] = v

    def edge(self, src: str, dst: str, kind: str, variant: str, conf: str, file=None, line=None) -> None:
        k = (src, dst, kind)
        cur = self.edges.setdefault(k, {"variants": set(), "confidence": conf, "file": file, "line": line})
        cur["variants"].add(variant)
        if _WEIGHT[conf] > _WEIGHT[cur["confidence"]]:
            cur["confidence"] = conf


def build_impact(before: list[Facts], after: list[Facts], dm: DiffMap, sel: TuSelection,
                 index: SymbolIndex | None, layers: LayerModel | None, cfg: AnalysisConfig) -> ImpactModel:
    fb = {f.usr: f for facts in before for f in facts.functions}
    fa = {f.usr: f for facts in after for f in facts.functions}
    b = _Builder()

    # 1. changed functions
    changed_status: dict[str, str] = {}
    for ch in dm.functions:
        if ch.kind == "removed":
            hit = [u for u, f in fb.items() if _overlaps(f, ch.file, ch.before_lines)]
            status = "removed"
        else:
            hit = [u for u, f in fa.items() if _overlaps(f, ch.file, ch.after_lines)]
            status = "added" if ch.kind == "added" else "changed"
        if not hit:
            pool = fb if ch.kind == "removed" else fa
            hit = [u for u, f in pool.items() if f.qualname == ch.qualname]
        for u in hit:
            changed_status[u] = status

    # 2. function nodes and call edges
    for variant, facts_list, funcs in (("before", before, fb), ("after", after, fa)):
        for facts in facts_list:
            heuristic = facts.tu.extractor == "treesitter"
            for f in facts.functions:
                b.node(f.usr, kind="function", label=f.qualname, file=f.file, line=f.start_line,
                       confidence="heuristic" if heuristic else "precise")
            for c in facts.calls:
                b.node(c.callee, kind="function", label=c.callee_name)
                b.edge(c.caller, c.callee, c.kind if c.kind == "virtual" else "call", variant,
                       "heuristic" if heuristic else c.confidence, c.file, c.line)
                if c.kind == "virtual":
                    mkey = c.callee.split("@F@", 1)[-1]
                    for other in funcs.values():
                        if other.method_key == mkey and other.usr != c.callee:
                            b.node(other.usr, kind="function", label=other.qualname, file=other.file,
                                   line=other.start_line)
                            b.edge(c.caller, other.usr, "virtual", variant, "may", c.file, c.line)
            for a in facts.fields:
                fkey = f"field:{a.field}"
                b.node(fkey, kind="field", label=f"{a.record}::{a.field_name}" if a.record else a.field_name)
                kind = "reads" if a.mode == "read" else "writes"
                conf = "heuristic" if heuristic else ("may" if a.confidence == "may" or a.mode == "may_write" else "precise")
                b.edge(a.fn, fkey, kind, variant, conf, a.file, a.line)

    # 3. heuristic edges from the symbol index for code outside the parsed TUs
    parsed = set(sel.selected)
    by_qual = {}
    for u, f in {**fb, **fa}.items():
        by_qual.setdefault(f.qualname, u)
    if index is not None:
        frontier = {(fa.get(u) or fb[u]).name: u for u in changed_status if (fa.get(u) or fb.get(u))}
        for _hop in range(cfg.caller_hops):
            nxt: dict[str, str] = {}
            for name, target in frontier.items():
                for row in index.callers_of(name):
                    if row.path in parsed or not row.caller:
                        continue
                    key = by_qual.get(row.caller) or f"ts:{row.path}#{row.caller}"
                    b.node(key, kind="function", label=row.caller, file=row.path, line=row.line,
                           confidence="heuristic")
                    b.edge(key, target, "call", "after", "heuristic", row.path, row.line)
                    nxt[row.caller.split("::")[-1]] = key
            frontier = nxt
        written = {(k[1], b.nodes[k[1]]["label"]) for k, e in b.edges.items()
                   if k[2] == "writes" and k[0] in changed_status}
        for fkey, label in written:
            fname = label.split("::")[-1]
            for row in index.member_refs(fname):
                if row.path in parsed or not row.fn:
                    continue
                key = by_qual.get(row.fn) or f"ts:{row.path}#{row.fn}"
                b.node(key, kind="function", label=row.fn, file=row.path, line=row.line, confidence="heuristic")
                b.edge(key, fkey, "writes" if row.is_write else "reads", "after", "heuristic", row.path, row.line)

    # 4. materialize with stable ids
    model = ImpactModel()
    key_to_id: dict[str, str] = {}
    for i, key in enumerate(sorted(b.nodes)):
        attrs = b.nodes[key]
        nid = f"N{i + 1}"
        key_to_id[key] = nid
        file = attrs.get("file")
        model.nodes[nid] = Node(
            id=nid, key=key, kind=attrs.get("kind", "function"), label=attrs.get("label", key),
            file=file, line=attrs.get("line"), status=changed_status.get(key, "unchanged"),
            layer=layers.level_of(file) if (layers and file) else None,
            confidence=attrs.get("confidence", "precise"))
    for i, (k, e) in enumerate(sorted(b.edges.items(), key=lambda kv: kv[0])):
        v = e["variants"]
        status = "unchanged" if len(v) == 2 else ("added" if "after" in v else "removed")
        model.edges.append(Edge(id=f"E{i + 1}", src=key_to_id[k[0]], dst=key_to_id[k[1]], kind=k[2],
                                status=status, confidence=e["confidence"], file=e["file"], line=e["line"]))
    model.changed = sorted((key_to_id[u] for u in changed_status if u in key_to_id), key=lambda s: int(s[1:]))

    _flows(model, cfg)
    _blast(model, cfg)
    _fanout(model, sel, index, layers)
    return model


def _flows(model: ImpactModel, cfg: AnalysisConfig) -> None:
    """Per changed function: callees down to flow_depth plus callers up to caller_hops."""
    out_edges: dict[str, list[Edge]] = {}
    in_edges: dict[str, list[Edge]] = {}
    for e in model.edges:
        if e.kind in ("call", "virtual"):
            out_edges.setdefault(e.src, []).append(e)
            in_edges.setdefault(e.dst, []).append(e)
    for root in model.changed:
        nodes, edges = [root], []
        seen, seen_edges = {root}, set()
        for adjacency, depth, forward in ((out_edges, cfg.flow_depth, True), (in_edges, cfg.caller_hops, False)):
            q = deque([(root, 0)])
            while q:
                n, d = q.popleft()
                if d >= depth:
                    continue
                for e in adjacency.get(n, []):
                    if e.id not in seen_edges:
                        seen_edges.add(e.id)
                        edges.append(e.id)
                    nxt = e.dst if forward else e.src
                    if nxt not in seen:
                        seen.add(nxt)
                        nodes.append(nxt)
                        q.append((nxt, d + 1))
        model.flows.append(Flow(root=root, nodes=nodes, edges=edges))


def _blast(model: ImpactModel, cfg: AnalysisConfig) -> None:
    incoming: dict[str, list[Edge]] = {}
    field_users: dict[str, list[Edge]] = {}
    writes_from: dict[str, list[Edge]] = {}
    for e in model.edges:
        if e.kind in ("call", "virtual"):
            incoming.setdefault(e.dst, []).append(e)
        elif e.status != "removed":
            field_users.setdefault(e.dst, []).append(e)
            if e.kind == "writes":
                writes_from.setdefault(e.src, []).append(e)
    seeds = set(model.changed)
    score: dict[str, float] = {}
    hop_of: dict[str, int] = {}
    via_of: dict[str, str] = {}
    pred: dict[str, str] = {}
    virtual_hit: set[str] = set()
    frontier = list(model.changed)
    for hop in range(1, cfg.blast_hops + 1):
        nxt: list[str] = []
        for n in frontier:
            reached: list[tuple[str, Edge, str]] = [(e.src, e, "call") for e in incoming.get(n, [])]
            if n in seeds:
                for w in writes_from.get(n, []):
                    for u in field_users.get(w.dst, []):
                        if u.src != n:
                            reached.append((u.src, u, "data"))
            for m, e, via in reached:
                if m in seeds:
                    continue
                score[m] = score.get(m, 0.0) + _WEIGHT[e.confidence] / hop
                if e.kind == "virtual":
                    virtual_hit.add(m)
                if m not in hop_of:
                    hop_of[m], via_of[m], pred[m] = hop, via, n
                    nxt.append(m)
        frontier = nxt
    layer_of = {nid: n.layer for nid, n in model.nodes.items()}
    for m, s in score.items():
        node = model.nodes[m]
        callers_layers = {layer_of[e.src] for e in incoming.get(m, [])}
        if any(l is not None and l != node.layer for l in callers_layers):
            s *= 1.5
        if any(fnmatch.fnmatchcase(node.label.split("::")[-1], p) for p in cfg.entrypoint_patterns):
            s *= 1.5
        if m in virtual_hit:
            s *= 1.3
        path = [m]
        while path[-1] in pred:
            path.append(pred[path[-1]])
        model.blast.append(BlastItem(node=m, hop=hop_of[m], score=round(s, 3), via=via_of[m], path=path))
    model.blast.sort(key=lambda x: (-x.score, x.hop, int(x.node[1:])))


def _fanout(model: ImpactModel, sel: TuSelection, index: SymbolIndex | None, layers: LayerModel | None) -> None:
    for header, total in sorted(sel.header_fanout.items()):
        by_layer: dict[str, int] = {}
        if index is not None and layers is not None:
            for p in index.transitive_includers(header):
                if is_header(p):
                    continue
                lv = layers.level_of(p)
                layer = layers.layer(lv)
                name = layer.name if layer else "unlayered"
                by_layer[name] = by_layer.get(name, 0) + 1
        model.fanout.append(FanOut(header=header, total_tus=total, by_layer=by_layer))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_impact.py -q`
Expected: `4 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `55 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_impact.py backend/codetortoise/impact.py
git commit -m "feat(backend): impact model with flows, blast radius and header fan-out"
```

---

### Task 12: Detectors: contract, field mutation, header fan-out

Deterministic rules over the impact model and facts, each emitting `Finding`s with evidence lines.

- **contract** — signature changes (callers must be re-checked) and new literal return values, classified per caller:
  ignores the result (medium), compares only with `==` against values that miss the new ones (high), range/`!=`
  comparisons (covered), uses without comparing (low); heuristic callers are counted.
- **field_mutation** — writes a changed function newly makes (or stopped making), keyed by field + root kind,
  including alias chains; high when other functions access the field, low when only may-writes.
- **header_fanout** — type/macro/prototype changes in headers, weighted by transitive TU count and layers reached.

Findings are sorted by severity and numbered `F1..`.

**Files:**
- Create: `backend/codetortoise/detectors/__init__.py`
- Create: `backend/codetortoise/detectors/base.py`
- Create: `backend/codetortoise/detectors/contract.py`
- Create: `backend/codetortoise/detectors/field_mutation.py`
- Create: `backend/codetortoise/detectors/header_fanout.py`
- Test: `backend/tests/test_detectors.py`

**Interfaces:**
- Consumes: `impact.ImpactModel`, `facts.model.Facts`, `diffmap.DiffMap`, `config.AnalysisConfig`.
- Produces: `Severity`, `SEVERITY_RANK`, `Evidence(text, file, line, severity)`, `Hypothesis(text, cites, verified)`,
  `Finding(id, kind, severity, title, nodes, evidence, summary, explanation, verify_steps, hypotheses, state)`,
  `DetectorContext(before, after, dm, impact, cfg)`, `max_severity(items, floor)`,
  `run_detectors(ctx, detectors=None) -> list[Finding]`; `detect_contract`, `detect_field_mutation`, `detect_header_fanout`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_detectors.py`:

```python
from codetortoise.detectors.base import DetectorContext, Evidence, max_severity, run_detectors


def findings_for(a):
    return run_detectors(DetectorContext(a.before, a.after, a.dm, a.impact, a.cfg))


def test_fixture_findings(analysed):
    findings = findings_for(analysed)
    got = [(f.id, f.severity, f.kind, f.title) for f in findings]
    assert got == [
        ("F1", "high", "field_mutation", "uart_send now writes Uart::errors through a local alias"),
        ("F2", "high", "header_fanout", "regs.h: 1 change(s) reach 4 TU(s)"),
        ("F3", "high", "header_fanout", "uart.h: 1 change(s) reach 3 TU(s)"),
        ("F4", "medium", "contract", "hal_write: signature changed"),
        ("F5", "medium", "contract", "uart_send: new return value(s) -2"),
        ("F6", "medium", "field_mutation", "uart_send now writes Stats::tx through a local alias"),
    ]
    f5 = findings[4]
    texts = [e.text for e in f5.evidence]
    assert "logger_flush ignores the result" in texts
    assert "logger_write checks ['!=0'] (covers new values)" in texts
    f1 = findings[0]
    assert f1.evidence[0].text == "write `u.errors` via err (precise)"
    assert "uart_errors" in f1.evidence[-1].text


def test_max_severity():
    assert max_severity([Evidence(text="a", severity="low"), Evidence(text="b", severity="high")]) == "high"
    assert max_severity([], floor="low") == "low"


def test_custom_detector_list_and_id_assignment(analysed):
    from codetortoise.detectors.base import Finding

    def fake(ctx):
        return [Finding(kind="z", severity="low", title="b", summary="s"),
                Finding(kind="a", severity="high", title="a", summary="s")]

    out = run_detectors(DetectorContext(analysed.before, analysed.after, analysed.dm, analysed.impact, analysed.cfg), [fake])
    assert [(f.id, f.kind) for f in out] == [("F1", "a"), ("F2", "z")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_detectors.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.detectors'`

- [ ] **Step 3: Implement**

`backend/codetortoise/detectors/__init__.py` — empty file.

`backend/codetortoise/detectors/base.py`:

```python
"""Finding model and detector registry."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts
from codetortoise.impact import ImpactModel

Severity = Literal["info", "low", "medium", "high"]
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


class Evidence(BaseModel):
    text: str
    file: str | None = None
    line: int | None = None
    severity: Severity = "info"


class Hypothesis(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)
    verified: bool = True


class Finding(BaseModel):
    id: str = ""
    kind: str
    severity: Severity
    title: str
    nodes: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    summary: str
    explanation: str | None = None
    verify_steps: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    state: Literal["open", "ack", "dismissed"] = "open"


@dataclass
class DetectorContext:
    before: list[Facts]
    after: list[Facts]
    dm: DiffMap
    impact: ImpactModel
    cfg: AnalysisConfig


Detector = Callable[[DetectorContext], list[Finding]]


def max_severity(items: list[Evidence], floor: Severity = "info") -> Severity:
    best = floor
    for e in items:
        if SEVERITY_RANK[e.severity] > SEVERITY_RANK[best]:
            best = e.severity
    return best


def run_detectors(ctx: DetectorContext, detectors: list[Detector] | None = None) -> list[Finding]:
    if detectors is None:
        from codetortoise.detectors.contract import detect_contract
        from codetortoise.detectors.field_mutation import detect_field_mutation
        from codetortoise.detectors.header_fanout import detect_header_fanout
        detectors = [detect_contract, detect_field_mutation, detect_header_fanout]
    findings: list[Finding] = []
    for d in detectors:
        findings.extend(d(ctx))
    findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.kind, f.title))
    for i, f in enumerate(findings):
        f.id = f"F{i + 1}"
    return findings
```

`backend/codetortoise/detectors/contract.py`:

```python
"""Contract changes: signatures, parameter const-ness, new return values vs caller handling."""
from __future__ import annotations

from codetortoise.detectors.base import DetectorContext, Evidence, Finding, max_severity

_RANGE_OPS = ("!=", "<", ">", "<=", ">=")


def _covered(compared: list[str], new_values: list[str]) -> bool:
    for c in compared:
        if c.startswith(_RANGE_OPS):
            return True
    return all(any(c == f"=={v}" for c in compared) for v in new_values)


def detect_contract(ctx: DetectorContext) -> list[Finding]:
    fb = {f.usr: f for facts in ctx.before for f in facts.functions}
    fa = {f.usr: f for facts in ctx.after for f in facts.functions}
    after_calls = [c for facts in ctx.after for c in facts.calls]
    findings = []
    for nid in ctx.impact.changed:
        node = ctx.impact.nodes[nid]
        before, after = fb.get(node.key), fa.get(node.key)
        if before is None or after is None:
            continue
        ev: list[Evidence] = []
        titles = []
        if before.signature != after.signature:
            titles.append("signature changed")
            ev.append(Evidence(text=f"signature: `{before.signature}` -> `{after.signature}`",
                               file=after.file, line=after.start_line, severity="medium"))
            callers = ctx.impact.edges_into(nid, {"call", "virtual"})
            if callers:
                names = sorted({ctx.impact.nodes[e.src].label for e in callers})
                ev.append(Evidence(text=f"{len(names)} caller(s) must be re-checked: {', '.join(names[:10])}",
                                   severity="medium"))
        new_values = [r for r in after.returns if r not in before.returns]
        if new_values:
            titles.append(f"new return value(s) {', '.join(new_values)}")
            ev.append(Evidence(text=f"returns before: {before.returns or ['(non-literal)']}; after: {after.returns}",
                               file=after.file, line=after.start_line, severity="low"))
            for c in after_calls:
                if c.callee != node.key:
                    continue
                caller = fa.get(c.caller)
                cname = caller.qualname if caller else c.caller
                if not c.result_used:
                    ev.append(Evidence(text=f"{cname} ignores the result", file=c.file, line=c.line,
                                       severity="medium"))
                elif c.compared and not _covered(c.compared, new_values):
                    ev.append(Evidence(text=f"{cname} checks {c.compared} which does not handle {new_values}",
                                       file=c.file, line=c.line, severity="high"))
                elif c.compared:
                    ev.append(Evidence(text=f"{cname} checks {c.compared} (covers new values)",
                                       file=c.file, line=c.line, severity="info"))
                else:
                    ev.append(Evidence(text=f"{cname} uses the result without comparing it",
                                       file=c.file, line=c.line, severity="low"))
            heur = [e for e in ctx.impact.edges_into(nid, {"call"}) if e.confidence == "heuristic"]
            if heur:
                ev.append(Evidence(text=f"{len(heur)} more caller(s) outside the parsed TUs (heuristic) not checked",
                                   severity="low"))
        if not ev:
            continue
        findings.append(Finding(
            kind="contract", severity=max_severity(ev), title=f"{after.qualname}: {'; '.join(titles)}",
            nodes=[nid], evidence=ev,
            summary=f"Contract of {after.qualname} changed ({'; '.join(titles)})."))
    return findings
```

`backend/codetortoise/detectors/field_mutation.py`:

```python
"""Field mutations introduced/removed by changed functions, including writes through local aliases."""
from __future__ import annotations

from collections import defaultdict

from codetortoise.detectors.base import DetectorContext, Evidence, Finding, max_severity
from codetortoise.facts.model import FieldAccess


def _writes(facts_list, usr: str) -> dict[tuple[str, str], list[FieldAccess]]:
    out: dict[tuple[str, str], list[FieldAccess]] = defaultdict(list)
    for facts in facts_list:
        for a in facts.fields:
            if a.fn == usr and a.mode != "read" and a.root_kind != "local":
                out[(a.field, a.root_kind)].append(a)
    return out


def detect_field_mutation(ctx: DetectorContext) -> list[Finding]:
    im = ctx.impact
    changed_ids = set(im.changed)
    findings = []
    for nid in im.changed:
        node = im.nodes[nid]
        wb, wa = _writes(ctx.before, node.key), _writes(ctx.after, node.key)
        for key in sorted(set(wa) - set(wb)):
            accesses = wa[key]
            a0 = accesses[0]
            field_node = im.node_by_key(f"field:{a0.field}")
            others = []
            if field_node is not None:
                others = sorted({im.nodes[e.src].label for e in im.edges
                                 if e.dst == field_node.id and e.src not in changed_ids and e.status != "removed"})
            only_may = all(a.mode == "may_write" for a in accesses)
            sev = "low" if only_may else ("high" if others else "medium")
            ev = []
            for a in accesses:
                how = f" via {' -> '.join(a.via)}" if a.via else ""
                ev.append(Evidence(text=f"{a.mode} `{a.path}`{how} ({a.confidence})", file=a.file, line=a.line,
                                   severity=sev))
            if others:
                ev.append(Evidence(text=f"{len(others)} other function(s) access this field: {', '.join(others[:10])}",
                                   severity=sev))
            label = field_node.label if field_node else a0.field_name
            alias = any(a.via for a in accesses)
            findings.append(Finding(
                kind="field_mutation", severity=max_severity(ev),
                title=f"{node.label} now writes {label}" + (" through a local alias" if alias else ""),
                nodes=[nid] + ([field_node.id] if field_node else []), evidence=ev,
                summary=f"{node.label} newly modifies {label} ({a0.path})."))
        for key in sorted(set(wb) - set(wa)):
            a0 = wb[key][0]
            findings.append(Finding(
                kind="field_mutation", severity="low", title=f"{node.label} no longer writes {a0.record}::{a0.field_name}",
                nodes=[nid], evidence=[Evidence(text=f"previously wrote `{a0.path}`", file=a0.file, line=a0.line,
                                                severity="low")],
                summary=f"{node.label} stopped modifying {a0.record}::{a0.field_name}; readers may depend on it."))
    return findings
```

`backend/codetortoise/detectors/header_fanout.py`:

```python
"""Header changes (types, macros, prototypes) weighted by how many TUs and layers include them."""
from __future__ import annotations

from codetortoise.cparse import is_header
from codetortoise.detectors.base import DetectorContext, Evidence, Finding


def detect_header_fanout(ctx: DetectorContext) -> list[Finding]:
    fan = {f.header: f for f in ctx.impact.fanout}
    by_header: dict[str, list[str]] = {}
    for t in ctx.dm.types:
        if is_header(t.file):
            by_header.setdefault(t.file, []).append(f"{t.kind.replace('_', ' ')}: {t.name}")
    findings = []
    for header, changes in sorted(by_header.items()):
        fo = fan.get(header)
        total = fo.total_tus if fo else 0
        layers = len(fo.by_layer) if fo else 0
        if total >= 100 or layers >= 3:
            sev = "high"
        elif total >= 10 or layers >= 2:
            sev = "medium"
        else:
            sev = "low"
        ev = [Evidence(text=c, file=header, severity=sev) for c in changes]
        if fo:
            ev.append(Evidence(text=f"included (transitively) by {total} TU(s); by layer: {fo.by_layer}",
                               severity=sev))
        findings.append(Finding(
            kind="header_fanout", severity=sev, title=f"{header.split('/')[-1]}: {len(changes)} change(s) reach {total} TU(s)",
            evidence=ev, summary=f"Changes in {header} affect {total} translation unit(s) across {layers} layer(s)."))
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_detectors.py -q`
Expected: `3 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `58 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_detectors.py backend/codetortoise/detectors/__init__.py backend/codetortoise/detectors/base.py backend/codetortoise/detectors/contract.py backend/codetortoise/detectors/field_mutation.py backend/codetortoise/detectors/header_fanout.py
git commit -m "feat(backend): contract, field-mutation and header fan-out detectors"
```

---

### Task 13: OpenAI-compatible LLM client

`POST {base_url}/chat/completions` with `response_format: json_object` (automatically dropped if the
server rejects it), 2 retries with backoff on transport errors/5xx/429, no retry on other 4xx, JSON extraction
tolerant of code fences, pydantic validation with one repair round. The API key is only ever placed in the
`Authorization` header.

**Files:**
- Create: `backend/codetortoise/llm/__init__.py`
- Create: `backend/codetortoise/llm/client.py`
- Test: `backend/tests/test_llm_client.py`

**Interfaces:**
- Produces: `LlmClient(base_url, api_key, model, timeout=120, transport=None, retries=2, sleep=time.sleep)` with
  `chat(system, user) -> str`, `complete_json(system, user, schema: type[T]) -> T`, `ping() -> bool`; `LlmError`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_llm_client.py`:

````python
import json

import httpx
import pytest
from pydantic import BaseModel

from codetortoise.llm.client import LlmClient, LlmError


class Out(BaseModel):
    answer: str
    n: int


def reply(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


def client(handler, **kw):
    return LlmClient("http://llm/v1", "sk-test", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_parses_json_and_sends_auth_and_response_format():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return reply('{"answer": "ok", "n": 2}')

    out = client(handler).complete_json("sys", "user", Out)
    assert out == Out(answer="ok", n=2)
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][1] == {"role": "user", "content": "user"}


def test_accepts_fenced_json():
    out = client(lambda r: reply('Here:\n```json\n{"answer": "x", "n": 1}\n```')).complete_json("s", "u", Out)
    assert out.n == 1


def test_repairs_invalid_json_once():
    replies = iter(['{"answer": "x"}', '{"answer": "x", "n": 3}'])
    prompts = []

    def handler(req):
        prompts.append(json.loads(req.content)["messages"][1]["content"])
        return reply(next(replies))

    assert client(handler).complete_json("s", "u", Out).n == 3
    assert "invalid" in prompts[1]


def test_invalid_twice_raises():
    with pytest.raises(LlmError, match="invalid JSON twice"):
        client(lambda r: reply("not json")).complete_json("s", "u", Out)


def test_retries_5xx_then_succeeds():
    codes = iter([500, 503, 200])

    def handler(req):
        c = next(codes)
        return reply('{"answer": "a", "n": 1}') if c == 200 else httpx.Response(c, text="busy")

    assert client(handler).complete_json("s", "u", Out).answer == "a"


def test_gives_up_after_retries():
    with pytest.raises(LlmError, match="after 3 attempts"):
        client(lambda r: httpx.Response(502)).chat("s", "u")


def test_falls_back_when_response_format_unsupported():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, text="unknown field response_format")
        return reply('{"answer": "a", "n": 1}')

    assert client(handler).complete_json("s", "u", Out).n == 1
    assert "response_format" not in bodies[-1]


def test_4xx_is_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with pytest.raises(LlmError, match="401"):
        client(handler).chat("s", "u")
    assert len(calls) == 1
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_llm_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.llm'`

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/__init__.py` — empty file.

`backend/codetortoise/llm/client.py`:

````python
"""OpenAI-compatible chat client with JSON output, retries and one repair round."""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LlmError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120,
                 transport: httpx.BaseTransport | None = None, retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.retries = retries
        self._sleep = sleep
        self._json_mode = True
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def chat(self, system: str, user: str) -> str:
        body = {"model": self.model, "temperature": 0.2,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            if self._json_mode:
                body["response_format"] = {"type": "json_object"}
            else:
                body.pop("response_format", None)
            try:
                r = self._http.post("/chat/completions", json=body)
            except httpx.HTTPError as e:
                last = e
            else:
                if r.status_code == 400 and self._json_mode and "response_format" in r.text:
                    self._json_mode = False
                    continue
                if r.status_code < 500 and r.status_code != 429:
                    if r.status_code >= 400:
                        raise LlmError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
                    try:
                        return r.json()["choices"][0]["message"]["content"] or ""
                    except (KeyError, IndexError, ValueError) as e:
                        raise LlmError(f"unexpected LLM response: {r.text[:300]}") from e
                last = LlmError(f"LLM HTTP {r.status_code}")
            if attempt < self.retries:
                self._sleep(2 ** attempt)
        raise LlmError(f"LLM request failed after {self.retries + 1} attempts: {last}")

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        system = system + "\n\nReply with a single JSON object matching this JSON schema:\n" + \
            json.dumps(schema.model_json_schema())
        text = self.chat(system, user)
        try:
            return schema.model_validate_json(_extract_json(text))
        except ValidationError as e:
            log.debug("LLM JSON invalid, repairing: %s", e)
            repair = (user + "\n\nYour previous reply was:\n" + text[:4000] +
                      f"\n\nIt was invalid: {str(e)[:1000]}\nReply again with valid JSON only.")
            text = self.chat(system, repair)
            try:
                return schema.model_validate_json(_extract_json(text))
            except ValidationError as e2:
                raise LlmError(f"LLM returned invalid JSON twice: {str(e2)[:300]}") from e2

    def ping(self) -> bool:
        try:
            return self._http.get("/models").status_code < 500
        except httpx.HTTPError:
            return False
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_llm_client.py -q`
Expected: `8 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `66 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_llm_client.py backend/codetortoise/llm/__init__.py backend/codetortoise/llm/client.py
git commit -m "feat(backend): OpenAI-compatible LLM client with JSON repair and retries"
```

---

### Task 14: Storyboard builder with grounding

Builds the storyboard in two layers. The **skeleton** is deterministic and always present: one chapter
per architectural layer (bottom-up), changed functions and findings attached, risk = highest open finding
severity, review order bottom-up. The **LLM pass** (optional) explains each finding (verification steps and
side-effect hypotheses), narrates each chapter with cross-layer effects, and writes the summary. Prompts carry
graph facts and code snippets under a token budget. **Grounding:** hypotheses and cross-layer effects must
cite known node/finding ids or they are dropped; unknown cites are stripped; a narrative without valid cites is
marked unverified. Any `LlmError` leaves the skeleton intact with `llm_error` set. `name_layers` asks the LLM to name inferred layers.

**Files:**
- Create: `backend/codetortoise/llm/storyboard.py`
- Test: `backend/tests/test_storyboard.py`

**Interfaces:**
- Consumes: `detectors.base.Finding/Hypothesis/SEVERITY_RANK`, `impact.ImpactModel`, `layers.LayerModel`, `llm.client`.
- Produces: `Cited(text, cites, verified)`, `Chapter(level, name, narrative, cites, verified, cross_layer_effects, nodes, findings)`,
  `Storyboard(summary, risk, review_order, verified, chapters, llm_used, llm_error)`,
  `skeleton(impact, findings, layers) -> Storyboard`, `ground(items, known) -> list[Cited]`, `budget(parts, max_tokens) -> str`,
  `build_storyboard(impact, findings, layers, snippets: dict[str, str], llm | None, max_tokens=64000) -> Storyboard`
  (mutates findings' `explanation`/`verify_steps`/`hypotheses`), `name_layers(model, llm) -> LayerModel`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_storyboard.py`:

```python
import json

import httpx

from codetortoise.detectors.base import Evidence, Finding
from codetortoise.impact import Edge, ImpactModel, Node
from codetortoise.layers import Layer, LayerModel
from codetortoise.llm.client import LlmClient
from codetortoise.llm.storyboard import Cited, budget, build_storyboard, ground, name_layers, skeleton


def model():
    im = ImpactModel()
    im.nodes = {
        "N1": Node(id="N1", key="c:@F@hal_write", label="hal_write", status="changed", layer=1, file="/w/hal/regs.c", line=3),
        "N2": Node(id="N2", key="c:@F@uart_send", label="uart_send", status="changed", layer=2, file="/w/d/uart.c", line=9),
        "N3": Node(id="N3", key="c:@F@logger_flush", label="logger_flush", layer=3),
    }
    im.edges = [Edge(id="E1", src="N3", dst="N2", kind="call"), Edge(id="E2", src="N2", dst="N1", kind="call")]
    im.changed = ["N1", "N2"]
    findings = [
        Finding(id="F1", kind="contract", severity="medium", title="uart_send: new return", nodes=["N2"],
                summary="s", evidence=[Evidence(text="logger_flush ignores the result")]),
        Finding(id="F2", kind="header_fanout", severity="high", title="regs.h", summary="s",
                evidence=[Evidence(text="decl changed", file="/w/include/hal/regs.h")]),
    ]
    layers = LayerModel(root="/w", layers=[Layer(level=0, name="L0: include/hal", modules=["include/hal"]),
                                           Layer(level=1, name="L1: hal", modules=["hal"]),
                                           Layer(level=2, name="L2: d", modules=["d"])],
                        module_level={"include/hal": 0, "hal": 1, "d": 2})
    return im, findings, layers


def test_skeleton_orders_chapters_bottom_up_and_attaches_findings():
    im, findings, layers = model()
    sb = skeleton(im, findings, layers)
    assert [(c.name, c.nodes, c.findings) for c in sb.chapters] == [
        ("L0: include/hal", [], ["F2"]), ("L1: hal", ["N1"], []), ("L2: d", ["N2"], ["F1"])]
    assert sb.risk == "high"
    assert sb.review_order == ["N1", "N2"]
    assert sb.summary == "2 function(s) changed across 2 layer(s); 2 finding(s), 1 high."
    assert not sb.llm_used


def test_ground_drops_uncited_and_unknown():
    items = [Cited(text="a", cites=["N1", "N99"]), Cited(text="b", cites=[]), Cited(text="c", cites=["X"])]
    assert ground(items, {"N1"}) == [Cited(text="a", cites=["N1"])]


def test_budget_truncates_by_priority():
    out = budget(["A" * 400, "B" * 400, "C" * 400], max_tokens=175)  # 700 chars
    assert out.startswith("A" * 400) and "B" in out and "C" not in out and out.endswith("[truncated]")


def fake_llm(responder):
    def handler(req):
        body = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
            responder(body["messages"][0]["content"], body["messages"][1]["content"]))}}]})
    return LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_llm_storyboard_is_grounded():
    im, findings, layers = model()

    def respond(system, user):
        if "Explain the risk" in user:
            return {"explanation": "exp", "verify_steps": ["check callers"],
                    "hypotheses": [{"text": "flush drops -2", "cites": ["N3", "F1"]},
                                   {"text": "made up", "cites": []}]}
        if "narrative for this architectural layer" in user:
            return {"narrative": "story", "cites": ["N2", "BOGUS"],
                    "cross_layer_effects": [{"text": "logger affected", "cites": ["N3"]}]}
        return {"summary": "sum", "risk": "medium", "review_order": ["N2", "N1", "NX"], "cites": ["F1"]}

    sb = build_storyboard(im, findings, layers, {"N2": "   9 int uart_send(...)"}, fake_llm(respond))
    assert sb.llm_used and sb.summary == "sum" and sb.risk == "medium"
    assert sb.review_order == ["N2", "N1"]
    assert findings[0].explanation == "exp" and findings[0].verify_steps == ["check callers"]
    assert [h.text for h in findings[0].hypotheses] == ["flush drops -2"]
    ch = sb.chapters[2]
    assert ch.narrative == "story" and ch.cites == ["N2"] and ch.verified
    assert [c.text for c in ch.cross_layer_effects] == ["logger affected"]


def test_llm_failure_keeps_deterministic_storyboard():
    im, findings, layers = model()
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                    sleep=lambda s: None)
    sb = build_storyboard(im, findings, layers, {}, llm)
    assert not sb.llm_used and "failed after" in sb.llm_error
    assert sb.chapters[1].narrative.startswith("Changed: hal_write")


def test_name_layers():
    _, _, layers = model()
    llm = fake_llm(lambda s, u: {"layers": [{"level": 0, "name": "HAL API", "description": "d"},
                                            {"level": 2, "name": "Drivers"}]})
    out = name_layers(layers, llm)
    assert [l.name for l in out.layers] == ["L0: HAL API", "L1: hal", "L2: Drivers"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_storyboard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.llm.storyboard'`

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/storyboard.py`:

```python
"""Storyboard: deterministic skeleton + optional grounded LLM narrative."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.detectors.base import SEVERITY_RANK, Finding, Hypothesis
from codetortoise.impact import ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.llm.client import LlmClient, LlmError

SYSTEM = ("You are a senior C/C++ code reviewer. You are given facts extracted by static analysis "
          "for a set of changes. Use ONLY these facts. Refer to functions/fields by their node id (e.g. N3) "
          "and to findings by their id (e.g. F2). Every claim must list the ids it relies on in `cites`. "
          "Be concise and concrete; prefer what a reviewer must verify.")


class Cited(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)
    verified: bool = True


class Chapter(BaseModel):
    level: int | None
    name: str
    narrative: str
    cites: list[str] = Field(default_factory=list)
    verified: bool = True
    cross_layer_effects: list[Cited] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    summary: str
    risk: Literal["low", "medium", "high"]
    review_order: list[str] = Field(default_factory=list)
    verified: bool = True
    chapters: list[Chapter] = Field(default_factory=list)
    llm_used: bool = False
    llm_error: str | None = None


class _ExplainOut(BaseModel):
    explanation: str
    verify_steps: list[str] = Field(default_factory=list)
    hypotheses: list[Cited] = Field(default_factory=list)


class _ChapterOut(BaseModel):
    narrative: str
    cites: list[str] = Field(default_factory=list)
    cross_layer_effects: list[Cited] = Field(default_factory=list)


class _SummaryOut(BaseModel):
    summary: str
    risk: Literal["low", "medium", "high"]
    review_order: list[str] = Field(default_factory=list)
    cites: list[str] = Field(default_factory=list)


class _LayerName(BaseModel):
    level: int
    name: str
    description: str = ""


class _LayerNamesOut(BaseModel):
    layers: list[_LayerName]


def ground(items: list[Cited], known: set[str]) -> list[Cited]:
    """Keep only items citing at least one known id; drop unknown ids from cites."""
    out = []
    for it in items:
        cites = [c for c in it.cites if c in known]
        if cites:
            out.append(Cited(text=it.text, cites=cites, verified=True))
    return out


def budget(parts: list[str], max_tokens: int) -> str:
    """Concatenate parts (already in priority order) until ~max_tokens (chars/4)."""
    limit = max_tokens * 4
    out, used = [], 0
    for p in parts:
        if used + len(p) > limit:
            remaining = limit - used
            if remaining > 200:
                out.append(p[:remaining] + "\n...[truncated]")
            break
        out.append(p)
        used += len(p)
    return "\n\n".join(out)


def _risk(findings: list[Finding]) -> str:
    top = max((SEVERITY_RANK[f.severity] for f in findings if f.state != "dismissed"), default=0)
    return "high" if top >= 3 else "medium" if top == 2 else "low"


def _finding_levels(f: Finding, impact: ImpactModel, layers: LayerModel | None) -> set[int | None]:
    levels = {impact.nodes[n].layer for n in f.nodes if n in impact.nodes and impact.nodes[n].kind == "function"}
    if not levels and layers is not None:
        levels = {layers.level_of(e.file) for e in f.evidence if e.file}
    return levels or {None}


def skeleton(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None) -> Storyboard:
    by_level: dict[int | None, Chapter] = {}

    def chapter(level: int | None) -> Chapter:
        if level not in by_level:
            layer = layers.layer(level) if layers is not None else None
            by_level[level] = Chapter(level=level, name=layer.name if layer else "Unlayered", narrative="")
        return by_level[level]

    for nid in impact.changed:
        chapter(impact.nodes[nid].layer).nodes.append(nid)
    for f in findings:
        for lv in _finding_levels(f, impact, layers):
            chapter(lv).findings.append(f.id)
    chapters = sorted(by_level.values(), key=lambda c: (c.level is None, c.level if c.level is not None else 0))
    for c in chapters:
        parts = [f"{impact.nodes[n].label} ({impact.nodes[n].status})" for n in c.nodes]
        c.narrative = (f"Changed: {', '.join(parts)}." if parts else "No functions changed in this layer.") + \
            (f" Findings: {', '.join(c.findings)}." if c.findings else "")
        c.cites = c.nodes + c.findings
    high = sum(1 for f in findings if f.severity == "high")
    summary = (f"{len(impact.changed)} function(s) changed across {len([c for c in chapters if c.nodes])} layer(s); "
               f"{len(findings)} finding(s), {high} high.")
    order = [n for c in chapters for n in c.nodes]
    return Storyboard(summary=summary, risk=_risk(findings), review_order=order, chapters=chapters)


def _node_line(impact: ImpactModel, nid: str) -> str:
    n = impact.nodes[nid]
    return f"{nid} {n.kind} {n.label} status={n.status} layer={n.layer} file={n.file}:{n.line}"


def _facts_for_nodes(impact: ImpactModel, nids: list[str]) -> str:
    lines = [_node_line(impact, n) for n in nids]
    ids = set(nids)
    for e in impact.edges:
        if e.src in ids or e.dst in ids:
            lines.append(f"{e.id}: {e.src} -{e.kind}/{e.status}/{e.confidence}-> {e.dst}")
    return "\n".join(lines[:400])


def _finding_text(f: Finding) -> str:
    ev = "\n".join(f"  - [{e.severity}] {e.text} ({e.file}:{e.line})" for e in f.evidence)
    return f"{f.id} [{f.severity}] {f.kind}: {f.title}\n{f.summary}\nnodes: {f.nodes}\nevidence:\n{ev}"


def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None,
                     snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000) -> Storyboard:
    sb = skeleton(impact, findings, layers)
    if llm is None:
        return sb
    known = set(impact.nodes) | {f.id for f in findings}
    per_call = max(2000, max_tokens // 2)
    try:
        for f in findings:
            nodes = [n for n in f.nodes if n in impact.nodes]
            neighbours = sorted({e.src for e in impact.edges if e.dst in nodes} |
                                {e.dst for e in impact.edges if e.src in nodes})
            parts = ["FINDING:\n" + _finding_text(f), "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes + neighbours)]
            parts += [f"CODE {n}:\n{snippets[n]}" for n in nodes + neighbours if n in snippets]
            out = llm.complete_json(SYSTEM, "Explain the risk of this finding, list concrete verification steps, "
                                    "and propose additional side-effect hypotheses (each citing ids).\n\n" +
                                    budget(parts, per_call), _ExplainOut)
            f.explanation = out.explanation
            f.verify_steps = out.verify_steps
            f.hypotheses = [Hypothesis(text=h.text, cites=h.cites) for h in ground(out.hypotheses, known)]
        for ch in sb.chapters:
            parts = [f"LAYER: {ch.name}",
                     "CHANGED NODES AND EDGES:\n" + _facts_for_nodes(impact, ch.nodes),
                     "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in findings if f.id in ch.findings)]
            parts += [f"CODE {n}:\n{snippets[n]}" for n in ch.nodes if n in snippets]
            out = llm.complete_json(SYSTEM, "Write the narrative for this architectural layer: what changed, why it "
                                    "matters, and effects on layers above/below (cross_layer_effects).\n\n" +
                                    budget(parts, per_call), _ChapterOut)
            ch.narrative = out.narrative
            ch.cites = [c for c in out.cites if c in known]
            ch.verified = bool(ch.cites)
            ch.cross_layer_effects = ground(out.cross_layer_effects, known)
        overview = [f"CHAPTER {c.name}: {c.narrative} (cites {c.cites})" for c in sb.chapters]
        overview += [_finding_text(f) for f in findings[:30]]
        out = llm.complete_json(SYSTEM, "Summarize the whole change for a reviewer in 3-6 sentences, give an overall "
                                "risk, and a review_order of node ids.\n\n" + budget(overview, per_call), _SummaryOut)
        sb.summary = out.summary
        sb.risk = out.risk
        order = [n for n in out.review_order if n in impact.nodes]
        sb.review_order = order or sb.review_order
        sb.verified = any(c in known for c in out.cites)
        sb.llm_used = True
    except LlmError as e:
        sb.llm_error = str(e)
    return sb


def name_layers(model: LayerModel, llm: LlmClient) -> LayerModel:
    listing = "\n".join(f"level {l.level}: modules {', '.join(l.modules[:40])}" for l in model.layers)
    out = llm.complete_json(
        "You name architectural layers of a C/C++ codebase. Level 0 is the lowest (no dependencies).",
        "Give each level a short name (1-3 words) and a one-sentence description.\n\n" + listing, _LayerNamesOut)
    names = {l.level: l for l in out.layers}
    for layer in model.layers:
        if layer.level in names:
            layer.name = f"L{layer.level}: {names[layer.level].name}"
            layer.description = names[layer.level].description
    return model
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_storyboard.py -q`
Expected: `6 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `72 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_storyboard.py backend/codetortoise/llm/storyboard.py
git commit -m "feat(backend): grounded storyboard builder"
```

---

### Task 15: SQLite store

Persistence for reviews and their CLs, per-stage status, stage outputs (JSON blobs), findings (with
ack/dismiss state that survives re-runs when kind+title match), threaded comments with anchors, hashed session
tokens with 7-day expiry, Swarm post records (idempotency) and a small key-value table (layer cache, layer
name overrides). Thread-safe via one connection guarded by a re-entrant lock, WAL mode.

**Files:**
- Create: `backend/codetortoise/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `detectors.base.Finding`, `vcs.model.ClMeta`.
- Produces: `Store(path)` with `create_review(title, created_by, cls) -> int`, `list_reviews()`, `get_review(rid)`,
  `set_review_status(rid, status, risk=None)`, `upsert_cl(rid, meta)`, `set_cl_swarm(rid, cl, swarm|None)`, `list_cls(rid)`,
  `reset_stages(rid, names)`, `set_stage(rid, name, status, message="")`, `list_stages(rid)`, `put_blob(rid, key, obj)`,
  `get_blob(rid, key)`, `put_findings(rid, findings)`, `list_findings(rid)`, `set_finding_state(rid, fid, state) -> bool`,
  `add_comment(rid, author, body, anchor_kind, anchor, parent_id=None) -> dict`, `get_comment(cid)`, `list_comments(rid)`,
  `update_comment(cid, body=None, resolved=None)`, `delete_comment(cid)`, `create_session(user, ttl_days=7) -> str`,
  `session_user(token) -> str | None`, `delete_session(token)`, `record_swarm_post(rid, cl, kind, swarm_id)`,
  `swarm_posts(rid, cl)`, `kv_get(key)`, `kv_put(key, obj)`; `ANCHOR_KINDS`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_store.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from codetortoise.detectors.base import Finding
from codetortoise.store import Store
from codetortoise.vcs.model import ClMeta


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


def test_reviews_and_cls(store):
    rid = store.create_review("t", "anoop", [5, 3, 5])
    assert store.get_review(rid)["cls"] == [3, 5]
    store.upsert_cl(rid, ClMeta(cl=3, status="pending", user="bob", description="d"))
    store.set_cl_swarm(rid, 3, {"id": 42})
    rows = store.list_cls(rid)
    assert rows[0]["status"] == "pending" and rows[0]["swarm"] == {"id": 42} and rows[1]["swarm"] is None
    store.set_review_status(rid, "done", "high")
    assert store.list_reviews()[0]["risk"] == "high"
    assert store.get_review(999) is None


def test_stages_and_blobs(store):
    rid = store.create_review("t", "a", [1])
    store.reset_stages(rid, ["ingest", "facts"])
    store.set_stage(rid, "ingest", "running")
    store.set_stage(rid, "ingest", "ok", "4 files")
    st = store.list_stages(rid)
    assert [(s["name"], s["status"]) for s in st] == [("ingest", "ok"), ("facts", "pending")]
    assert st[0]["started_at"] and st[0]["finished_at"]
    store.put_blob(rid, "k", {"a": [1, 2]})
    store.put_blob(rid, "m", [Finding(kind="x", severity="low", title="t", summary="s")])
    assert store.get_blob(rid, "k") == {"a": [1, 2]}
    assert store.get_blob(rid, "m")[0]["title"] == "t"
    assert store.get_blob(rid, "missing") is None


def test_finding_state_survives_rerun(store):
    rid = store.create_review("t", "a", [1])
    store.put_findings(rid, [Finding(id="F1", kind="contract", severity="high", title="a", summary="s")])
    assert store.set_finding_state(rid, "F1", "dismissed")
    store.put_findings(rid, [Finding(id="F1", kind="contract", severity="high", title="a", summary="s"),
                             Finding(id="F2", kind="contract", severity="low", title="b", summary="s")])
    assert [(f.id, f.state) for f in store.list_findings(rid)] == [("F1", "dismissed"), ("F2", "open")]
    assert not store.set_finding_state(rid, "F9", "ack")


def test_comments(store):
    rid = store.create_review("t", "a", [1])
    c = store.add_comment(rid, "bob", "hi", "line", {"depot": "//d/a.c", "line": 3})
    r = store.add_comment(rid, "amy", "re", "line", {"depot": "//d/a.c", "line": 3}, parent_id=c["id"])
    assert c["anchor"] == {"depot": "//d/a.c", "line": 3} and c["resolved"] is False
    assert store.update_comment(c["id"], resolved=True)["resolved"] is True
    assert store.update_comment(c["id"], body="hello")["edited_at"]
    store.delete_comment(c["id"])
    assert store.list_comments(rid) == [] and store.get_comment(r["id"]) is None
    with pytest.raises(ValueError):
        store.add_comment(rid, "bob", "x", "bogus", {})


def test_sessions(store):
    tok = store.create_session("bob")
    assert store.session_user(tok) == "bob"
    assert store.session_user("nope") is None and store.session_user(None) is None
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    store._exec("UPDATE sessions SET expires_at=?", (past,))
    assert store.session_user(tok) is None
    tok2 = store.create_session("amy")
    store.delete_session(tok2)
    assert store.session_user(tok2) is None


def test_swarm_posts_and_kv(store):
    store.record_swarm_post(1, 7, "summary", "99")
    assert [p["swarm_id"] for p in store.swarm_posts(1, 7)] == ["99"]
    store.kv_put("x", {"a": 1})
    assert store.kv_get("x") == {"a": 1} and store.kv_get("y") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.store'`

- [ ] **Step 3: Implement**

`backend/codetortoise/store.py`:

```python
"""SQLite persistence for reviews, stage outputs, findings, comments, sessions."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from codetortoise.detectors.base import Finding
from codetortoise.vcs.model import ClMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_by TEXT,
  created_at TEXT, status TEXT, risk TEXT);
CREATE TABLE IF NOT EXISTS review_cls(review_id INTEGER, cl INTEGER, status TEXT, user TEXT,
  description TEXT, swarm_json TEXT, PRIMARY KEY(review_id, cl));
CREATE TABLE IF NOT EXISTS stages(review_id INTEGER, name TEXT, status TEXT, message TEXT,
  started_at TEXT, finished_at TEXT, PRIMARY KEY(review_id, name));
CREATE TABLE IF NOT EXISTS blobs(review_id INTEGER, key TEXT, json TEXT, PRIMARY KEY(review_id, key));
CREATE TABLE IF NOT EXISTS findings(review_id INTEGER, id TEXT, severity TEXT, kind TEXT, title TEXT,
  json TEXT, state TEXT, PRIMARY KEY(review_id, id));
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, parent_id INTEGER,
  author TEXT, body TEXT, anchor_kind TEXT, anchor_json TEXT, resolved INTEGER DEFAULT 0,
  created_at TEXT, edited_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user TEXT, created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS swarm_posts(review_id INTEGER, cl INTEGER, kind TEXT, swarm_id TEXT, posted_at TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, json TEXT);
"""

ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _dump(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        return obj.model_dump_json()
    if isinstance(obj, list) and obj and isinstance(obj[0], BaseModel):
        return "[" + ",".join(o.model_dump_json() for o in obj) + "]"
    return json.dumps(obj)


class Store:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._db:
            return self._db.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # ---- reviews ---------------------------------------------------------
    def create_review(self, title: str, created_by: str, cls: list[int]) -> int:
        cur = self._exec("INSERT INTO reviews(title, created_by, created_at, status, risk) VALUES(?,?,?,?,?)",
                         (title, created_by, _now(), "queued", None))
        rid = int(cur.lastrowid)
        for cl in sorted(set(cls)):
            self._exec("INSERT INTO review_cls(review_id, cl, status) VALUES(?,?,?)", (rid, cl, "unknown"))
        return rid

    def _with_cls(self, r: dict) -> dict:
        r["cls"] = [row["cl"] for row in self._all("SELECT cl FROM review_cls WHERE review_id=? ORDER BY cl",
                                                    (r["id"],))]
        return r

    def list_reviews(self) -> list[dict]:
        return [self._with_cls(r) for r in self._all("SELECT * FROM reviews ORDER BY id DESC")]

    def get_review(self, rid: int) -> dict | None:
        rows = self._all("SELECT * FROM reviews WHERE id=?", (rid,))
        return self._with_cls(rows[0]) if rows else None

    def set_review_status(self, rid: int, status: str, risk: str | None = None) -> None:
        if risk is None:
            self._exec("UPDATE reviews SET status=? WHERE id=?", (status, rid))
        else:
            self._exec("UPDATE reviews SET status=?, risk=? WHERE id=?", (status, risk, rid))

    def upsert_cl(self, rid: int, meta: ClMeta) -> None:
        self._exec("INSERT INTO review_cls(review_id, cl, status, user, description) VALUES(?,?,?,?,?) "
                   "ON CONFLICT(review_id, cl) DO UPDATE SET status=excluded.status, user=excluded.user, "
                   "description=excluded.description", (rid, meta.cl, meta.status, meta.user, meta.description))

    def set_cl_swarm(self, rid: int, cl: int, swarm: dict | None) -> None:
        self._exec("UPDATE review_cls SET swarm_json=? WHERE review_id=? AND cl=?",
                   (json.dumps(swarm) if swarm is not None else None, rid, cl))

    def list_cls(self, rid: int) -> list[dict]:
        out = []
        for r in self._all("SELECT * FROM review_cls WHERE review_id=? ORDER BY cl", (rid,)):
            r["swarm"] = json.loads(r.pop("swarm_json")) if r.get("swarm_json") else None
            out.append(r)
        return out

    # ---- stages & blobs --------------------------------------------------
    def reset_stages(self, rid: int, names: list[str]) -> None:
        self._exec("DELETE FROM stages WHERE review_id=?", (rid,))
        for n in names:
            self._exec("INSERT INTO stages(review_id, name, status, message) VALUES(?,?,?,?)", (rid, n, "pending", ""))

    def set_stage(self, rid: int, name: str, status: str, message: str = "") -> None:
        if status == "running":
            self._exec("UPDATE stages SET status=?, message=?, started_at=? WHERE review_id=? AND name=?",
                       (status, message, _now(), rid, name))
        else:
            self._exec("UPDATE stages SET status=?, message=?, finished_at=? WHERE review_id=? AND name=?",
                       (status, message, _now(), rid, name))

    def list_stages(self, rid: int) -> list[dict]:
        return self._all("SELECT name, status, message, started_at, finished_at FROM stages WHERE review_id=? "
                         "ORDER BY rowid", (rid,))

    def put_blob(self, rid: int, key: str, obj: Any) -> None:
        self._exec("INSERT OR REPLACE INTO blobs(review_id, key, json) VALUES(?,?,?)", (rid, key, _dump(obj)))

    def get_blob(self, rid: int, key: str) -> Any:
        rows = self._all("SELECT json FROM blobs WHERE review_id=? AND key=?", (rid, key))
        return json.loads(rows[0]["json"]) if rows else None

    # ---- findings --------------------------------------------------------
    def put_findings(self, rid: int, findings: list[Finding]) -> None:
        """Replace findings; keep ack/dismiss state for findings with the same (kind, title)."""
        old = {(r["kind"], r["title"]): r["state"] for r in
               self._all("SELECT kind, title, state FROM findings WHERE review_id=?", (rid,))}
        self._exec("DELETE FROM findings WHERE review_id=?", (rid,))
        for f in findings:
            f.state = old.get((f.kind, f.title), f.state)
            self._exec("INSERT INTO findings(review_id, id, severity, kind, title, json, state) VALUES(?,?,?,?,?,?,?)",
                       (rid, f.id, f.severity, f.kind, f.title, f.model_dump_json(), f.state))

    def list_findings(self, rid: int) -> list[Finding]:
        out = []
        for r in self._all("SELECT json, state FROM findings WHERE review_id=? ORDER BY rowid", (rid,)):
            f = Finding.model_validate_json(r["json"])
            f.state = r["state"]
            out.append(f)
        return out

    def set_finding_state(self, rid: int, fid: str, state: str) -> bool:
        cur = self._exec("UPDATE findings SET state=? WHERE review_id=? AND id=?", (state, rid, fid))
        return cur.rowcount > 0

    # ---- comments --------------------------------------------------------
    def add_comment(self, rid: int, author: str, body: str, anchor_kind: str, anchor: dict,
                    parent_id: int | None = None) -> dict:
        if anchor_kind not in ANCHOR_KINDS:
            raise ValueError(f"bad anchor kind {anchor_kind}")
        cur = self._exec("INSERT INTO comments(review_id, parent_id, author, body, anchor_kind, anchor_json, "
                         "created_at) VALUES(?,?,?,?,?,?,?)",
                         (rid, parent_id, author, body, anchor_kind, json.dumps(anchor), _now()))
        return self.get_comment(int(cur.lastrowid))

    def _comment(self, r: dict) -> dict:
        r["anchor"] = json.loads(r.pop("anchor_json"))
        r["resolved"] = bool(r["resolved"])
        return r

    def get_comment(self, cid: int) -> dict | None:
        rows = self._all("SELECT * FROM comments WHERE id=?", (cid,))
        return self._comment(rows[0]) if rows else None

    def list_comments(self, rid: int) -> list[dict]:
        return [self._comment(r) for r in self._all("SELECT * FROM comments WHERE review_id=? ORDER BY id", (rid,))]

    def update_comment(self, cid: int, body: str | None = None, resolved: bool | None = None) -> dict | None:
        if body is not None:
            self._exec("UPDATE comments SET body=?, edited_at=? WHERE id=?", (body, _now(), cid))
        if resolved is not None:
            self._exec("UPDATE comments SET resolved=? WHERE id=?", (int(resolved), cid))
        return self.get_comment(cid)

    def delete_comment(self, cid: int) -> None:
        self._exec("DELETE FROM comments WHERE id=? OR parent_id=?", (cid, cid))

    # ---- sessions --------------------------------------------------------
    def create_session(self, user: str, ttl_days: int = 7) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._exec("INSERT INTO sessions VALUES(?,?,?,?)",
                   (_hash(token), user, now.isoformat(), (now + timedelta(days=ttl_days)).isoformat()))
        return token

    def session_user(self, token: str | None) -> str | None:
        if not token:
            return None
        rows = self._all("SELECT user, expires_at FROM sessions WHERE token_hash=?", (_hash(token),))
        if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
            return None
        return rows[0]["user"]

    def delete_session(self, token: str) -> None:
        self._exec("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))

    # ---- swarm posts & kv ------------------------------------------------
    def record_swarm_post(self, rid: int, cl: int, kind: str, swarm_id: str) -> None:
        self._exec("INSERT INTO swarm_posts VALUES(?,?,?,?,?)", (rid, cl, kind, swarm_id, _now()))

    def swarm_posts(self, rid: int, cl: int) -> list[dict]:
        return self._all("SELECT kind, swarm_id, posted_at FROM swarm_posts WHERE review_id=? AND cl=?", (rid, cl))

    def kv_get(self, key: str) -> Any:
        rows = self._all("SELECT json FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["json"]) if rows else None

    def kv_put(self, key: str, obj: Any) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, _dump(obj)))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_store.py -q`
Expected: `6 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `78 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_store.py backend/codetortoise/store.py
git commit -m "feat(backend): SQLite store for reviews, findings, comments and sessions"
```

---

### Task 16: Swarm client

Swarm REST API v9 (supported by Swarm 2019.1+), authenticated with the owner's P4 user + ticket:
read the review for a change (normalized to id/state/author/votes/url), create a review for a shelved change,
post a comment on a review. Errors raise `SwarmError`; callers treat Swarm as non-blocking.

**Files:**
- Create: `backend/codetortoise/swarm.py`
- Test: `backend/tests/test_swarm.py`

**Interfaces:**
- Produces: `SwarmClient(base_url, user, ticket, transport=None, timeout=30)` with `get_review_for_change(cl) -> dict | None`,
  `create_review(cl, description) -> dict`, `post_comment(review_id, body) -> str`, `version() -> dict`; `SwarmError`.
- Review dict: `{"id", "state", "state_label", "author", "votes": {user: value}, "url"}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_swarm.py`:

```python
import httpx
import pytest

from codetortoise.swarm import SwarmClient, SwarmError

REVIEW = {"id": 42, "state": "needsReview", "stateLabel": "Needs Review", "author": "bob",
          "participants": {"bob": [], "amy": {"vote": {"value": 1, "version": 2}}}}


def client(handler):
    return SwarmClient("https://swarm.example.com/", "anoop", "TICKET", transport=httpx.MockTransport(handler))


def test_get_review_for_change_normalizes():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={"reviews": [REVIEW]})

    r = client(handler).get_review_for_change(123)
    assert r == {"id": 42, "state": "needsReview", "state_label": "Needs Review", "author": "bob",
                 "votes": {"amy": 1}, "url": "https://swarm.example.com/reviews/42"}
    assert "change%5B%5D=123" in seen["url"] and seen["auth"].startswith("Basic ")


def test_no_review_returns_none():
    assert client(lambda r: httpx.Response(200, json={"reviews": []})).get_review_for_change(1) is None


def test_create_and_comment_send_form_data():
    bodies = []

    def handler(req):
        bodies.append((req.method, req.url.path, req.content.decode()))
        if req.url.path.endswith("/reviews"):
            return httpx.Response(200, json={"review": REVIEW})
        return httpx.Response(200, json={"comment": {"id": 7}})

    c = client(handler)
    assert c.create_review(123, "desc")["id"] == 42
    assert c.post_comment(42, "hello world") == "7"
    assert bodies[0] == ("POST", "/api/v9/reviews", "change=123&description=desc")
    assert bodies[1] == ("POST", "/api/v9/comments", "topic=reviews%2F42&body=hello+world")


def test_http_error_raises():
    with pytest.raises(SwarmError, match="HTTP 403"):
        client(lambda r: httpx.Response(403, text="denied")).get_review_for_change(1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_swarm.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.swarm'`

- [ ] **Step 3: Implement**

`backend/codetortoise/swarm.py`:

```python
"""Minimal P4 Swarm REST client (API v9): read review, create review, post comment."""
from __future__ import annotations

import httpx


class SwarmError(RuntimeError):
    pass


def _summary(base: str, r: dict) -> dict:
    votes = {}
    participants = r.get("participants") or {}
    if isinstance(participants, dict):
        for user, p in participants.items():
            vote = (p or {}).get("vote") if isinstance(p, dict) else None
            if isinstance(vote, dict):
                votes[user] = vote.get("value", 0)
    return {"id": r.get("id"), "state": r.get("state"), "state_label": r.get("stateLabel", r.get("state")),
            "author": r.get("author"), "votes": votes, "url": f"{base}/reviews/{r.get('id')}"}


class SwarmClient:
    def __init__(self, base_url: str, user: str, ticket: str, transport: httpx.BaseTransport | None = None,
                 timeout: float = 30):
        self.base = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base, auth=(user, ticket), timeout=timeout, transport=transport)

    def _req(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise SwarmError(f"swarm {method} {path}: {e}") from e
        if r.status_code >= 400:
            raise SwarmError(f"swarm {method} {path}: HTTP {r.status_code} {r.text[:300]}")
        return r.json()

    def get_review_for_change(self, cl: int) -> dict | None:
        data = self._req("GET", "/api/v9/reviews", params={"change[]": cl, "max": 1})
        reviews = data.get("reviews") or []
        return _summary(self.base, reviews[0]) if reviews else None

    def create_review(self, cl: int, description: str) -> dict:
        data = self._req("POST", "/api/v9/reviews", data={"change": cl, "description": description})
        return _summary(self.base, data.get("review") or {})

    def post_comment(self, review_id: int | str, body: str) -> str:
        data = self._req("POST", "/api/v9/comments", data={"topic": f"reviews/{review_id}", "body": body})
        return str((data.get("comment") or {}).get("id", ""))

    def version(self) -> dict:
        return self._req("GET", "/api/version")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_swarm.py -q`
Expected: `4 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `82 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_swarm.py backend/codetortoise/swarm.py
git commit -m "feat(backend): Swarm v9 client"
```

---

### Task 17: Services, review pipeline, job runner, health checks

`build_services` wires config into long-lived objects (store, source, symbol index, compile DB, toolchain,
LLM client, cached layer model). `run_review` executes the stages
`ingest → swarm_read → diffmap → tu_select → layers → facts → impact → detectors → llm → finalize` with isolation:
each stage records `ok | degraded | failed | skipped` plus a message, and a stage is skipped only when a stage
it depends on did not produce output. The final review status is `done`, `degraded` or `failed`. `JobRunner` runs reviews and index
rebuilds one at a time on a background thread. `run_health` implements the startup checks; hard failures block review creation.

**Files:**
- Create: `backend/codetortoise/services.py`
- Create: `backend/codetortoise/pipeline.py`
- Create: `backend/codetortoise/health.py`
- Test: `backend/tests/helpers.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: all backend modules above.
- Produces: `Services(cfg, store, source, index, cdb, toolchain, llm, layers, p4=None, owner_ticket=None, swarm_override=None)`
  with `swarm() -> SwarmClient | None`; `LayersProvider.get() -> LayerModel | None`; `make_llm(cfg)`;
  `build_services(cfg, llm=None, source=None) -> Services`.
- Produces: `STAGES`, `DEPS`, `Degraded`, `run_review(rid, svc)`, `collect_snippets(impact, cs, after)`,
  `JobRunner(svc)` with `start()`, `submit_review(rid)`, `submit_index()`, `stop()`, `index_building`.
- Produces: `Check(name, ok, hard, detail)`, `HealthReport(checks, ready, index_generation, libclang, strip_flags)`, `run_health(svc)`.
- Blob keys written: `changeset`, `diffmap`, `selection`, `layers`, `facts_before`, `facts_after`, `impact`, `storyboard`.
- Test helpers: `tests/helpers.py` → `make_config(fx, data_dir, **overrides)`, `make_services(fx, data_dir, **kw)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/helpers.py`:

```python
from pathlib import Path

from codetortoise.config import Config
from codetortoise.services import build_services


def make_config(fx, data_dir: Path, **overrides) -> Config:
    raw = {
        "owner": "owner",
        "server": {"data_dir": str(data_dir), "public_url": "http://tortoise.local:8765"},
        "workspace": {"vcs": "git", "root": str(fx.root), "compile_commands": str(fx.compile_commands)},
        "auth": {"mode": "dev"},
        "analysis": {"module_min_files": 1, "workers": 1},
    }
    raw.update(overrides)
    return Config.model_validate(raw)


def make_services(fx, data_dir: Path, **kw):
    return build_services(make_config(fx, data_dir), **kw)
```

`backend/tests/test_pipeline.py`:

```python
from helpers import make_services

from codetortoise.health import run_health
from codetortoise.pipeline import run_review
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def stages(svc, rid):
    return {s["name"]: s["status"] for s in svc.store.list_stages(rid)}


def test_full_review_without_llm_or_swarm(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok",
                                "llm": "degraded", "finalize": "ok"}
    review = svc.store.get_review(rid)
    assert review["status"] == "degraded" and review["risk"] == "high"
    assert len(svc.store.list_findings(rid)) == 6
    sb = svc.store.get_blob(rid, "storyboard")
    assert [c["name"] for c in sb["chapters"]][:3] == ["L0: cpp, include/hal", "L1: hal", "L2: driver"]
    assert [c["cl"] for c in svc.store.list_cls(rid)] == [101, 102]
    assert svc.store.list_cls(rid)[0]["description"].startswith("uart:")


def test_ingest_failure_skips_dependent_stages(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [999])
    run_review(rid, svc)
    st = stages(svc, rid)
    assert st["ingest"] == "failed" and st["diffmap"] == "skipped" and st["detectors"] == "skipped"
    assert "CL 999 not found" in svc.store.list_stages(rid)[0]["message"]
    assert svc.store.get_review(rid)["status"] == "failed"


class OnlyDocs:
    def load(self, cls):
        return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                         files=[FileChange(depot="//d/README.md", local="/nowhere/README.md", action="edit",
                                           before="a", after="b")])


def test_change_without_c_code_completes(fx, tmp_path):
    svc = make_services(fx, tmp_path, source=OnlyDocs())
    rid = svc.store.create_review("t", "owner", [1])
    run_review(rid, svc)
    st = stages(svc, rid)
    assert st["impact"] == "ok" and st["detectors"] == "ok"
    assert svc.store.list_findings(rid) == []
    assert svc.store.get_blob(rid, "storyboard")["risk"] == "low"


def test_health_ready_on_fixture_and_gates_on_empty_compile_db(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rep = run_health(svc)
    assert rep.ready and rep.libclang.startswith("clang version")
    assert {c.name: c.ok for c in rep.checks}["llm endpoint"] is False  # warning only
    svc.cdb.entries.clear()
    assert run_health(svc).ready is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.services'`

- [ ] **Step 3: Implement**

`backend/codetortoise/services.py`:

```python
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
```

`backend/codetortoise/pipeline.py`:

```python
"""Staged review pipeline and background job runner."""
from __future__ import annotations

import logging
import queue
import threading
import traceback
from pathlib import Path

from codetortoise.detectors.base import DetectorContext, run_detectors
from codetortoise.diffmap import map_changes
from codetortoise.facts.model import Facts
from codetortoise.facts.runner import build_requests, run_extraction
from codetortoise.impact import ImpactModel, build_impact
from codetortoise.llm.storyboard import build_storyboard
from codetortoise.services import Services
from codetortoise.swarm import SwarmError
from codetortoise.tu_select import select_tus
from codetortoise.vcs.model import ChangeSet

log = logging.getLogger(__name__)

STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "llm", "finalize"]
DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "llm": ["detectors"]}


class Degraded(Exception):
    """Stage completed with a warning; its outputs are usable."""


def _snippet(text: str, start: int, end: int, max_lines: int = 120) -> str:
    lines = text.splitlines()
    chunk = lines[max(0, start - 1): min(len(lines), end, start - 1 + max_lines)]
    return "\n".join(f"{start + i:5d} {l}" for i, l in enumerate(chunk))


def collect_snippets(impact: ImpactModel, cs: ChangeSet, after: list[Facts], limit: int = 40) -> dict[str, str]:
    texts = {f.local: f.after for f in cs.files}
    ends = {f.usr: f.end_line for facts in after for f in facts.functions}
    wanted = list(impact.changed) + [b.node for b in impact.blast[:limit]]
    out = {}
    for nid in wanted:
        n = impact.nodes[nid]
        if n.kind != "function" or not n.file or not n.line:
            continue
        text = texts.get(n.file)
        if text is None:
            p = Path(n.file)
            text = p.read_text(errors="replace") if p.exists() else ""
        out[nid] = _snippet(text, n.line, ends.get(n.key, n.line + 40))
    return out


def run_review(rid: int, svc: Services) -> None:
    store, cfg = svc.store, svc.cfg
    store.reset_stages(rid, STAGES)
    store.set_review_status(rid, "running")
    status: dict[str, str] = {}
    ctx: dict = {}
    cls = store.get_review(rid)["cls"]

    def stage(name: str, fn) -> None:
        if any(status.get(d) not in ("ok", "degraded") for d in DEPS.get(name, [])):
            status[name] = "skipped"
            store.set_stage(rid, name, "skipped", "missing inputs")
            return
        store.set_stage(rid, name, "running")
        try:
            msg = fn() or ""
            status[name] = "ok"
            store.set_stage(rid, name, "ok", msg)
        except Degraded as e:
            status[name] = "degraded"
            store.set_stage(rid, name, "degraded", str(e))
        except Exception as e:  # stage isolation: record and continue
            log.error("stage %s failed: %s", name, traceback.format_exc())
            status[name] = "failed"
            store.set_stage(rid, name, "failed", f"{type(e).__name__}: {e}")

    def ingest():
        cs = svc.source.load(cls)
        ctx["cs"] = cs
        for meta in cs.cls:
            store.upsert_cl(rid, meta)
        store.put_blob(rid, "changeset", cs)
        return f"{len(cs.files)} file(s), {len(cs.drift)} drift warning(s)"

    def swarm_read():
        client = svc.swarm()
        if client is None:
            raise Degraded("Swarm not configured or owner not logged in")
        errors = []
        for meta in ctx["cs"].cls:
            try:
                store.set_cl_swarm(rid, meta.cl, client.get_review_for_change(meta.cl))
            except SwarmError as e:
                errors.append(str(e))
        if errors:
            raise Degraded("; ".join(errors))

    def diffmap():
        dm = map_changes(ctx["cs"])
        ctx["dm"] = dm
        store.put_blob(rid, "diffmap", dm)
        return f"{len(dm.functions)} function change(s), {len(dm.types)} type/macro/decl change(s)"

    def tu_select():
        if svc.index.generation() == 0:
            svc.index.build(cfg.workspace.root, workers=cfg.analysis.workers)
        sel = select_tus(ctx["dm"], svc.index, svc.cdb, cfg.analysis)
        ctx["sel"] = sel
        store.put_blob(rid, "selection", sel)
        return f"{len(sel.selected)} TU(s) selected, {sel.over_budget} over budget"

    def layers():
        model = svc.layers.get()
        ctx["layers"] = model
        if model is None:
            raise Degraded("symbol index not built yet")
        store.put_blob(rid, "layers", model)
        return f"{len(model.layers)} layer(s)"

    def facts():
        svc.toolchain.prepare()
        lib = svc.toolchain.libclang.path if svc.toolchain.libclang and svc.toolchain.libclang.vendor else None
        before = run_extraction(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "before"), lib, cfg.analysis.workers)
        after = run_extraction(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "after"), lib, cfg.analysis.workers)
        ctx["before"], ctx["after"] = before, after
        store.put_blob(rid, "facts_before", before)
        store.put_blob(rid, "facts_after", after)
        bad = [f.tu.file for f in before + after if f.tu.confidence != "precise"]
        if bad:
            raise Degraded(f"{len(bad)} TU parse(s) degraded or fell back to tree-sitter")
        return f"{len(before) + len(after)} TU parse(s)"

    def impact():
        im = build_impact(ctx["before"], ctx["after"], ctx["dm"], ctx["sel"], svc.index, ctx.get("layers"), cfg.analysis)
        ctx["impact"] = im
        store.put_blob(rid, "impact", im)
        return f"{len(im.nodes)} node(s), {len(im.edges)} edge(s), blast {len(im.blast)}"

    def detectors():
        findings = run_detectors(DetectorContext(ctx["before"], ctx["after"], ctx["dm"], ctx["impact"], cfg.analysis))
        ctx["findings"] = findings
        store.put_findings(rid, findings)
        return f"{len(findings)} finding(s)"

    def llm():
        findings = store.list_findings(rid)
        snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
        sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens)
        store.put_findings(rid, findings)
        store.put_blob(rid, "storyboard", sb)
        ctx["storyboard"] = sb
        if svc.llm is None:
            raise Degraded("no LLM configured; deterministic storyboard only")
        if sb.llm_error:
            raise Degraded(sb.llm_error)

    def finalize():
        sb = ctx.get("storyboard")
        if status.get("ingest") != "ok":
            store.set_review_status(rid, "failed")
        elif all(status.get(s) == "ok" for s in STAGES if s != "finalize"):
            store.set_review_status(rid, "done", sb.risk if sb else None)
        else:
            store.set_review_status(rid, "degraded", sb.risk if sb else None)

    for name, fn in [("ingest", ingest), ("swarm_read", swarm_read), ("diffmap", diffmap), ("tu_select", tu_select),
                     ("layers", layers), ("facts", facts), ("impact", impact), ("detectors", detectors),
                     ("llm", llm), ("finalize", finalize)]:
        stage(name, fn)


class JobRunner:
    """Single background worker: reviews and index rebuilds run one at a time."""

    def __init__(self, svc: Services):
        self.svc = svc
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tortoise-jobs")
        self.index_building = False

    def start(self) -> None:
        self._thread.start()

    def submit_review(self, rid: int) -> None:
        self.svc.store.set_review_status(rid, "queued")
        self._q.put(("review", rid))

    def submit_index(self) -> None:
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
                    run_review(arg, self.svc)
                elif kind == "index":
                    self.index_building = True
                    self.svc.index.build(self.svc.cfg.workspace.root, workers=self.svc.cfg.analysis.workers)
            except Exception:
                log.error("job %s failed: %s", job, traceback.format_exc())
            finally:
                self.index_building = False
```

`backend/codetortoise/health.py`:

```python
"""Startup validation. Hard checks gate review creation."""
from __future__ import annotations

from pydantic import BaseModel

from codetortoise.services import Services
from codetortoise.vcs.p4runner import P4Error


class Check(BaseModel):
    name: str
    ok: bool
    hard: bool
    detail: str = ""


class HealthReport(BaseModel):
    checks: list[Check]
    ready: bool
    index_generation: int = 0
    libclang: str | None = None
    strip_flags: list[str] = []


def run_health(svc: Services) -> HealthReport:
    cfg = svc.cfg
    ws = cfg.workspace
    checks: list[Check] = []
    checks.append(Check(name="workspace root", ok=ws.root.is_dir(), hard=True, detail=str(ws.root)))
    if ws.vcs == "p4" and svc.p4 is not None:
        try:
            recs = svc.p4.run("client", "-o", ws.client or "")
            root = recs[0].get("Root", "") if recs else ""
            ok = bool(root) and str(ws.root).rstrip("/") == root.rstrip("/")
            checks.append(Check(name="p4 client", ok=ok, hard=True,
                                detail=f"client {ws.client} Root={root}" + ("" if ok else f" (config root {ws.root})")))
        except P4Error as e:
            checks.append(Check(name="p4 client", ok=False, hard=True, detail=str(e)))
    checks.append(Check(name="compile_commands", ok=bool(svc.cdb.entries), hard=True,
                        detail=f"{len(svc.cdb.entries)} entries in {ws.compile_commands}"))
    try:
        svc.toolchain.prepare()
        lc = svc.toolchain.libclang
        checks.append(Check(name="libclang", ok=True, hard=True,
                            detail=f"{lc.version} ({'vendor' if lc.vendor else 'bundled'}) {lc.path}"))
    except (OSError, RuntimeError) as e:
        checks.append(Check(name="libclang", ok=False, hard=True, detail=str(e)))
    if cfg.toolchain.clang:
        err = svc.toolchain.driver_error
        checks.append(Check(name="driver query", ok=err is None, hard=False,
                            detail=err or f"langs: {sorted(svc.toolchain.driver)}"))
    if svc.llm is not None:
        checks.append(Check(name="llm endpoint", ok=svc.llm.ping(), hard=False, detail=cfg.llm.base_url or ""))
    else:
        checks.append(Check(name="llm endpoint", ok=False, hard=False, detail="not configured"))
    if cfg.swarm.url:
        client = svc.swarm()
        checks.append(Check(name="swarm", ok=client is not None, hard=False,
                            detail=cfg.swarm.url if client else "owner must log in for Swarm access"))
    lc = svc.toolchain.libclang
    return HealthReport(checks=checks, ready=all(c.ok for c in checks if c.hard),
                        index_generation=svc.index.generation(),
                        libclang=lc.version if lc else None, strip_flags=sorted(svc.toolchain.strip))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py -q`
Expected: `4 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `86 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/helpers.py backend/tests/test_pipeline.py backend/codetortoise/services.py backend/codetortoise/pipeline.py backend/codetortoise/health.py
git commit -m "feat(backend): review pipeline with stage isolation, job runner and health checks"
```

---

### Task 18: Web API (FastAPI)

JSON API under `/api` plus SPA fallback. Auth: `POST /api/login` validates with `p4 login -p` (or any
username in `auth.mode: dev`), creates an HTTP-only session cookie, and keeps the owner's ticket in memory for
Swarm. Owner-only: create/re-run reviews, health, index rebuild, finding state, layer renames, Swarm actions.
Everyone signed in: view everything, comment (edit own; delete own, owner deletes any; anyone resolves).
`/api/reviews/{id}/events` streams stage progress as server-sent events until the review is terminal.
Swarm posting is idempotent unless `confirm_repeat` is sent.

**Files:**
- Create: `backend/codetortoise/web/__init__.py`
- Create: `backend/codetortoise/web/app.py`
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: `Services`, `JobRunner`, `run_health`, `SwarmError`, `P4Error`.
- Produces: `create_app(svc, runner, authenticate) -> FastAPI`, `make_authenticator(svc)` (`(user, password) -> ticket | None`), `COOKIE`.
- Routes: `POST /api/login|logout`, `GET /api/me`, `GET /api/health`, `POST /api/index/rebuild`, `GET|POST /api/reviews`,
  `GET /api/reviews/{rid}`, `POST /api/reviews/{rid}/rerun`, `GET /api/reviews/{rid}/events|storyboard|impact|findings|files|comments`,
  `PATCH /api/reviews/{rid}/findings/{fid}`, `PUT /api/layers/{level}`, `POST /api/reviews/{rid}/comments`,
  `PATCH|DELETE /api/comments/{cid}`, `POST /api/reviews/{rid}/cls/{cl}/swarm/refresh|create|post`, `GET /{path}` (SPA).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_web.py`:

```python
import pytest
from fastapi.testclient import TestClient
from helpers import make_services

from codetortoise.pipeline import JobRunner, run_review
from codetortoise.web.app import create_app, make_authenticator


class InlineRunner(JobRunner):
    """Runs jobs synchronously so tests are deterministic."""

    def submit_review(self, rid):
        run_review(rid, self.svc)

    def submit_index(self):
        self.svc.index.build(self.svc.cfg.workspace.root)


class FakeSwarm:
    def __init__(self):
        self.posts = []

    def get_review_for_change(self, cl):
        return {"id": 42, "state": "needsReview", "url": "https://swarm/reviews/42", "votes": {}}

    def create_review(self, cl, desc):
        return {"id": 77, "state": "needsReview", "url": "https://swarm/reviews/77", "votes": {}}

    def post_comment(self, review_id, body):
        self.posts.append((review_id, body))
        return "c1"


@pytest.fixture
def env(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    swarm = FakeSwarm()
    svc.swarm_override = lambda: swarm
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    return svc, app, swarm


def login(app, user):
    c = TestClient(app)
    assert c.post("/api/login", json={"user": user, "password": "x"}).status_code == 200
    return c


def test_auth_required_and_me(env):
    _, app, _ = env
    assert TestClient(app).get("/api/reviews").status_code == 401
    c = login(app, "owner")
    assert c.get("/api/me").json() == {"user": "owner", "is_owner": True, "swarm_ready": True}
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401


def test_owner_creates_review_others_view_and_comment(env):
    svc, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    assert bob.post("/api/reviews", json={"cls": [101]}).status_code == 403
    r = owner.post("/api/reviews", json={"cls": [102, 101]})
    assert r.status_code == 200 and r.json()["title"] == "CLs 101, 102"
    rid = r.json()["id"]
    detail = bob.get(f"/api/reviews/{rid}").json()
    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 10
    assert bob.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["risk"] == "high"
    assert len(bob.get(f"/api/reviews/{rid}/impact").json()["nodes"]) > 5
    assert len(bob.get(f"/api/reviews/{rid}/findings").json()) == 6
    assert [f["depot"] for f in bob.get(f"/api/reviews/{rid}/files").json()][0] == "//fixture/driver/uart.c"
    ev = bob.get(f"/api/reviews/{rid}/events")
    assert ev.status_code == 200 and ev.text.startswith("data: ")

    c = bob.post(f"/api/reviews/{rid}/comments",
                 json={"body": "why -2?", "anchor_kind": "line", "anchor": {"depot": "//fixture/driver/uart.c", "line": 18}})
    cid = c.json()["id"]
    assert c.json()["author"] == "bob"
    reply = owner.post(f"/api/reviews/{rid}/comments",
                       json={"body": "overflow", "anchor_kind": "line", "anchor": {}, "parent_id": cid})
    assert reply.json()["parent_id"] == cid
    assert owner.patch(f"/api/comments/{cid}", json={"body": "hijack"}).status_code == 403
    assert owner.patch(f"/api/comments/{cid}", json={"resolved": True}).json()["resolved"] is True
    assert bob.delete(f"/api/comments/{reply.json()['id']}").status_code == 403
    assert owner.delete(f"/api/comments/{cid}").status_code == 200
    assert bob.get(f"/api/reviews/{rid}/comments").json() == []


def test_finding_state_owner_only(env):
    _, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    assert bob.patch(f"/api/reviews/{rid}/findings/F1", json={"state": "ack"}).status_code == 403
    assert owner.patch(f"/api/reviews/{rid}/findings/F1", json={"state": "ack"}).status_code == 200
    assert owner.get(f"/api/reviews/{rid}/findings").json()[0]["state"] == "ack"
    assert owner.patch(f"/api/reviews/{rid}/findings/F99", json={"state": "ack"}).status_code == 404


def test_swarm_actions(env):
    svc, app, swarm = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    cls = owner.get(f"/api/reviews/{rid}").json()["cls"]
    assert cls[0]["swarm"]["id"] == 42  # swarm_read stage used the (fake) client
    assert owner.post(f"/api/reviews/{rid}/cls/101/swarm/create").status_code == 409  # submitted CL
    r = owner.post(f"/api/reviews/{rid}/cls/101/swarm/post", json={})
    assert r.status_code == 200 and swarm.posts[0][0] == 42
    assert "http://tortoise.local:8765/r/" + str(rid) in swarm.posts[0][1]
    assert owner.post(f"/api/reviews/{rid}/cls/101/swarm/post", json={}).status_code == 409
    assert owner.post(f"/api/reviews/{rid}/cls/101/swarm/post", json={"confirm_repeat": True}).status_code == 200
    assert owner.post(f"/api/reviews/{rid}/cls/555/swarm/refresh").status_code == 404


def test_health_and_layer_rename(env):
    _, app, _ = env
    owner = login(app, "owner")
    h = owner.get("/api/health").json()
    assert h["ready"] is True and {c["name"] for c in h["checks"]} >= {"workspace root", "compile_commands", "libclang"}
    assert owner.put("/api/layers/2", json={"name": "Drivers"}).json() == {"2": "Drivers"}
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    names = [c["name"] for c in owner.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["chapters"]]
    assert "Drivers" in names and "L2: driver" not in names
    assert login(app, "bob").put("/api/layers/2", json={"name": "x"}).status_code == 403


def test_review_creation_blocked_when_not_ready(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cdb.entries.clear()  # hard check fails: empty compile DB
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    owner = login(app, "owner")
    assert owner.post("/api/reviews", json={"cls": [101]}).status_code == 409


def test_spa_fallback_and_api_404(env):
    _, app, _ = env
    c = TestClient(app)
    assert c.get("/r/1").status_code == 200
    assert c.get("/api/nope").status_code in (401, 404)


def test_p4_authenticator_rejects_without_runner(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cfg.auth.mode = "p4"
    auth = make_authenticator(svc)
    assert auth("bob", "pw") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_web.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.web'`

- [ ] **Step 3: Implement**

`backend/codetortoise/web/__init__.py` — empty file.

`backend/codetortoise/web/app.py`:

```python
"""FastAPI application: JSON API under /api, React SPA everywhere else."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from codetortoise.health import run_health
from codetortoise.pipeline import JobRunner
from codetortoise.services import Services
from codetortoise.swarm import SwarmError
from codetortoise.vcs.p4runner import P4Error

COOKIE = "ct_session"
STATIC = Path(__file__).parent / "static"
TERMINAL = {"done", "degraded", "failed"}


class LoginIn(BaseModel):
    user: str
    password: str = ""


class ReviewIn(BaseModel):
    cls: list[int] = Field(min_length=1)
    title: str | None = None


class FindingStateIn(BaseModel):
    state: Literal["open", "ack", "dismissed"]


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    anchor_kind: Literal["line", "function", "finding", "chapter", "review"]
    anchor: dict = Field(default_factory=dict)
    parent_id: int | None = None


class CommentPatch(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    resolved: bool | None = None


class SwarmPostIn(BaseModel):
    confirm_repeat: bool = False


class LayerNameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
    """authenticate(user, password) -> ticket str on success, None on failure."""
    app = FastAPI(title="CodeTortoise")
    store, cfg = svc.store, svc.cfg
    state = {"ready": run_health(svc).ready}

    def user_of(request: Request) -> str:
        user = store.session_user(request.cookies.get(COOKIE))
        if user is None:
            raise HTTPException(401, "login required")
        return user

    def owner_of(user: str = Depends(user_of)) -> str:
        if user != cfg.owner:
            raise HTTPException(403, "owner only")
        return user

    def review_or_404(rid: int) -> dict:
        r = store.get_review(rid)
        if r is None:
            raise HTTPException(404, "review not found")
        return r

    # ---- auth --------------------------------------------------------------
    @app.post("/api/login")
    def login(body: LoginIn, response: Response):
        ticket = authenticate(body.user, body.password)
        if ticket is None:
            raise HTTPException(401, "invalid credentials")
        if body.user == cfg.owner:
            svc.owner_ticket = ticket
        token = store.create_session(body.user)
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400)
        return {"user": body.user, "is_owner": body.user == cfg.owner}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            store.delete_session(tok)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: str = Depends(user_of)):
        return {"user": user, "is_owner": user == cfg.owner, "swarm_ready": svc.swarm() is not None}

    # ---- health / index -------------------------------------------------------
    @app.get("/api/health")
    def health(_: str = Depends(owner_of)):
        rep = run_health(svc)
        state["ready"] = rep.ready
        return {**rep.model_dump(), "index_building": runner.index_building}

    @app.post("/api/index/rebuild")
    def rebuild_index(_: str = Depends(owner_of)):
        runner.submit_index()
        return {"queued": True}

    # ---- reviews ------------------------------------------------------------
    @app.get("/api/reviews")
    def list_reviews(_: str = Depends(user_of)):
        return store.list_reviews()

    @app.post("/api/reviews")
    def create_review(body: ReviewIn, user: str = Depends(owner_of)):
        if not state["ready"]:
            raise HTTPException(409, "startup checks failing; see Health")
        title = body.title or "CLs " + ", ".join(str(c) for c in sorted(set(body.cls)))
        rid = store.create_review(title, user, body.cls)
        runner.submit_review(rid)
        return store.get_review(rid)

    @app.get("/api/reviews/{rid}")
    def get_review(rid: int, _: str = Depends(user_of)):
        return {"review": review_or_404(rid), "cls": store.list_cls(rid), "stages": store.list_stages(rid)}

    @app.post("/api/reviews/{rid}/rerun")
    def rerun(rid: int, _: str = Depends(owner_of)):
        review_or_404(rid)
        runner.submit_review(rid)
        return {"queued": True}

    @app.get("/api/reviews/{rid}/events")
    async def events(rid: int, request: Request, _: str = Depends(user_of)):
        review_or_404(rid)

        async def gen():
            last = None
            while not await request.is_disconnected():
                payload = json.dumps({"review": store.get_review(rid), "stages": store.list_stages(rid)})
                if payload != last:
                    last = payload
                    yield f"data: {payload}\n\n"
                if store.get_review(rid)["status"] in TERMINAL:
                    return
                await asyncio.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/reviews/{rid}/storyboard")
    def storyboard(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        cs = store.get_blob(rid, "changeset") or {}
        sb, layers = store.get_blob(rid, "storyboard"), store.get_blob(rid, "layers")
        overrides = store.kv_get("layer_overrides") or {}
        for item in (sb or {}).get("chapters", []) + (layers or {}).get("layers", []):
            if str(item.get("level")) in overrides:
                item["name"] = overrides[str(item["level"])]
        return {"storyboard": sb, "drift": cs.get("drift", []), "layers": layers}

    @app.get("/api/reviews/{rid}/impact")
    def impact(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        return store.get_blob(rid, "impact")

    @app.get("/api/reviews/{rid}/findings")
    def findings(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        return [f.model_dump() for f in store.list_findings(rid)]

    @app.patch("/api/reviews/{rid}/findings/{fid}")
    def finding_state(rid: int, fid: str, body: FindingStateIn, _: str = Depends(owner_of)):
        if not store.set_finding_state(rid, fid, body.state):
            raise HTTPException(404, "finding not found")
        return {"ok": True}

    @app.get("/api/reviews/{rid}/files")
    def files(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        cs = store.get_blob(rid, "changeset") or {}
        return cs.get("files", [])

    # ---- layers ------------------------------------------------------------
    @app.put("/api/layers/{level}")
    def rename_layer(level: int, body: LayerNameIn, _: str = Depends(owner_of)):
        overrides = store.kv_get("layer_overrides") or {}
        overrides[str(level)] = body.name
        store.kv_put("layer_overrides", overrides)
        return overrides

    # ---- comments ----------------------------------------------------------
    @app.get("/api/reviews/{rid}/comments")
    def comments(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        return store.list_comments(rid)

    @app.post("/api/reviews/{rid}/comments")
    def add_comment(rid: int, body: CommentIn, user: str = Depends(user_of)):
        review_or_404(rid)
        if body.parent_id is not None:
            parent = store.get_comment(body.parent_id)
            if parent is None or parent["review_id"] != rid:
                raise HTTPException(400, "bad parent_id")
        return store.add_comment(rid, user, body.body, body.anchor_kind, body.anchor, body.parent_id)

    @app.patch("/api/comments/{cid}")
    def edit_comment(cid: int, body: CommentPatch, user: str = Depends(user_of)):
        c = store.get_comment(cid)
        if c is None:
            raise HTTPException(404, "comment not found")
        if body.body is not None and c["author"] != user:
            raise HTTPException(403, "only the author can edit")
        return store.update_comment(cid, body=body.body, resolved=body.resolved)

    @app.delete("/api/comments/{cid}")
    def delete_comment(cid: int, user: str = Depends(user_of)):
        c = store.get_comment(cid)
        if c is None:
            raise HTTPException(404, "comment not found")
        if c["author"] != user and user != cfg.owner:
            raise HTTPException(403, "only the author or owner can delete")
        store.delete_comment(cid)
        return {"ok": True}

    # ---- swarm ---------------------------------------------------------------
    def swarm_client():
        client = svc.swarm()
        if client is None:
            raise HTTPException(409, "Swarm not configured or owner not logged in")
        return client

    def cl_row(rid: int, cl: int) -> dict:
        row = next((c for c in store.list_cls(rid) if c["cl"] == cl), None)
        if row is None:
            raise HTTPException(404, "CL not in review")
        return row

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/refresh")
    def swarm_refresh(rid: int, cl: int, _: str = Depends(owner_of)):
        cl_row(rid, cl)
        try:
            data = swarm_client().get_review_for_change(cl)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/create")
    def swarm_create(rid: int, cl: int, _: str = Depends(owner_of)):
        row = cl_row(rid, cl)
        if row["status"] != "pending":
            raise HTTPException(409, "only pending (shelved) CLs can get a new Swarm review")
        if row.get("swarm"):
            raise HTTPException(409, "CL already has a Swarm review")
        try:
            data = swarm_client().create_review(cl, row.get("description") or f"CL {cl}")
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        store.record_swarm_post(rid, cl, "create", str(data.get("id")))
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/post")
    def swarm_post(rid: int, cl: int, body: SwarmPostIn, _: str = Depends(owner_of)):
        row = cl_row(rid, cl)
        if not row.get("swarm"):
            raise HTTPException(409, "CL has no Swarm review")
        if any(p["kind"] == "summary" for p in store.swarm_posts(rid, cl)) and not body.confirm_repeat:
            raise HTTPException(409, "summary already posted; resend with confirm_repeat")
        sb = store.get_blob(rid, "storyboard") or {}
        link = f"{cfg.server.public_url.rstrip('/')}/r/{rid}"
        text = f"CodeTortoise review (risk: {sb.get('risk', 'n/a')}): {sb.get('summary', '')}\n\nFull storyboard: {link}"
        try:
            cid = swarm_client().post_comment(row["swarm"]["id"], text)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.record_swarm_post(rid, cl, "summary", cid)
        return {"comment_id": cid}

    # ---- SPA -------------------------------------------------------------------
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = STATIC / path
        if path and target.is_file() and STATIC in target.resolve().parents:
            return FileResponse(target)
        index = STATIC / "index.html"
        if index.exists():
            return FileResponse(index)
        return Response("frontend not built; run `npm run build` in frontend/", media_type="text/plain")

    return app


def make_authenticator(svc: Services):
    if svc.cfg.auth.mode == "dev":
        return lambda user, password: "" if user else None

    def p4_auth(user: str, password: str) -> str | None:
        if svc.p4 is None or not user:
            return None
        try:
            return svc.p4.login_check(user, password)
        except P4Error:
            return None
    return p4_auth
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_web.py -q`
Expected: `8 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `94 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_web.py backend/codetortoise/web/__init__.py backend/codetortoise/web/app.py
git commit -m "feat(backend): FastAPI app with P4 auth, reviews, comments and Swarm actions"
```

---

### Task 19: CLI: serve, index, headless review, fixture demo

`codetortoise serve` (starts the job runner, queues an index build on first start, runs uvicorn),
`index` (rebuild symbol index), `review` (run the pipeline headless and print stages and findings — the fastest
iteration loop on real CLs), `fixture-demo` (materialize the bundled fixture and write a ready-to-serve dev config).

**Files:**
- Create: `backend/codetortoise/cli.py`
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, `build_services`, `JobRunner`, `run_review`, `create_app`, `make_authenticator`, `build_fixture`.
- Produces: `main(argv=None) -> int` (exit 2 on `ConfigError`); console script `codetortoise`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_cli.py`:

```python
import yaml

from codetortoise.cli import main


def test_fixture_demo_then_headless_review(tmp_path, capsys):
    assert main(["fixture-demo", "--dir", str(tmp_path), "--port", "9999"]) == 0
    cfg = yaml.safe_load((tmp_path / "tortoise.yaml").read_text())
    assert cfg["workspace"]["vcs"] == "git" and cfg["auth"]["mode"] == "dev" and cfg["server"]["port"] == 9999
    capsys.readouterr()
    assert main(["review", "--config", str(tmp_path / "tortoise.yaml"), "101"]) == 0
    out = capsys.readouterr().out
    assert "uart_send now writes Uart::errors through a local alias" in out
    assert "review 1: degraded" in out


def test_bad_config_exit_code(tmp_path, capsys):
    (tmp_path / "bad.yaml").write_text("owner: x\n")
    assert main(["index", "--config", str(tmp_path / "bad.yaml")]) == 2
    assert "config error" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.cli'`

- [ ] **Step 3: Implement**

`backend/codetortoise/cli.py`:

```python
"""Command line: serve, index, review (headless), fixture-demo."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from codetortoise.config import ConfigError, load_config


def _services(config: str):
    from codetortoise.services import build_services
    return build_services(load_config(Path(config)))


def cmd_serve(args) -> int:
    import uvicorn

    from codetortoise.pipeline import JobRunner
    from codetortoise.web.app import create_app, make_authenticator
    svc = _services(args.config)
    runner = JobRunner(svc)
    runner.start()
    if svc.index.generation() == 0:
        runner.submit_index()
    app = create_app(svc, runner, make_authenticator(svc))
    if svc.cfg.auth.mode == "dev":
        logging.warning("auth.mode=dev: any username logs in without a password. Do not expose this server.")
    uvicorn.run(app, host=svc.cfg.server.host, port=svc.cfg.server.port)
    return 0


def cmd_index(args) -> int:
    svc = _services(args.config)
    n = svc.index.build(svc.cfg.workspace.root, workers=svc.cfg.analysis.workers)
    print(f"indexed {n} files (generation {svc.index.generation()})")
    return 0


def cmd_review(args) -> int:
    from codetortoise.pipeline import run_review
    svc = _services(args.config)
    rid = svc.store.create_review(args.title or f"CLs {args.cls}", svc.cfg.owner, args.cls)
    run_review(rid, svc)
    for s in svc.store.list_stages(rid):
        print(f"{s['name']:<11} {s['status']:<9} {s['message']}")
    for f in svc.store.list_findings(rid):
        print(f"{f.id:>4} {f.severity:<7} {f.kind:<15} {f.title}")
        for e in f.evidence:
            loc = f" ({e.file}:{e.line})" if e.file else ""
            print(f"       - {e.text}{loc}")
    print(f"review {rid}: {svc.store.get_review(rid)['status']}")
    return 0


def cmd_fixture_demo(args) -> int:
    from codetortoise.fixture import build_fixture
    dest = Path(args.dir).resolve()
    fx = build_fixture(dest)
    cfg = {
        "owner": "demo",
        "server": {"host": "127.0.0.1", "port": args.port, "public_url": f"http://127.0.0.1:{args.port}",
                   "data_dir": str(dest / "data")},
        "workspace": {"vcs": "git", "root": str(fx.root), "compile_commands": str(fx.compile_commands)},
        "auth": {"mode": "dev"},
        "analysis": {"module_min_files": 1, "workers": 1},
    }
    if args.llm_base_url:
        cfg["llm"] = {"base_url": args.llm_base_url, "model": args.llm_model}
    path = dest / "tortoise.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"fixture workspace: {fx.root}\nconfig: {path}\nCLs: {fx.cls}\n"
          f"run: codetortoise serve --config {path}   (log in as 'demo')")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="codetortoise")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--config", required=True)
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("index", help="(re)build the repo-wide symbol index")
    s.add_argument("--config", required=True)
    s.set_defaults(fn=cmd_index)
    s = sub.add_parser("review", help="run a review headless and print findings")
    s.add_argument("--config", required=True)
    s.add_argument("--title")
    s.add_argument("cls", nargs="+", type=int)
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("fixture-demo", help="create a demo workspace + config from the bundled fixture")
    s.add_argument("--dir", required=True)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--llm-base-url")
    s.add_argument("--llm-model", default="gpt-4o-mini")
    s.set_defaults(fn=cmd_fixture_demo)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_cli.py -q`
Expected: `2 passed`

- [ ] **Step 5: Lint and run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `96 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_cli.py backend/codetortoise/cli.py
git commit -m "feat(backend): CLI with serve, index, headless review and fixture demo"
```

---

### Task 20: Frontend tooling, typed API client, diff and graph helpers

React + TypeScript + Vite project whose build lands in `backend/codetortoise/web/static` (served by
FastAPI). `api.ts` mirrors the backend JSON types. Two pure helpers carry the logic worth unit-testing:
`diffRows` (numbered unified diff with collapsed context) and `flowElements`/`blastRings` (cytoscape elements
for before/after/diff call-flow views; blast rings by hop).

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/types.d.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/lib/diffRows.ts`
- Create: `frontend/src/lib/graph.ts`
- Test: `frontend/src/lib/diffRows.test.ts`
- Test: `frontend/src/lib/graph.test.ts`

**Interfaces:**
- Consumes: backend JSON shapes from Task 18.
- Produces: `api` object (one method per route) and the exported types (`Me`, `ReviewRow`, `Stage`, `ClRow`, `ReviewDetail`,
  `Node`, `Edge`, `Flow`, `BlastItem`, `FanOut`, `Impact`, `Evidence`, `Cited`, `Finding`, `Chapter`, `Storyboard`,
  `Drift`, `StoryboardResponse`, `FileChange`, `AnchorKind`, `Comment`, `Health`), `ApiError`.
- Produces: `diffRows(before, after, context=3) -> Row[]`, `flowElements(impact, roots, mode, showData) -> GraphElement[]`,
  `blastRings(impact) -> Map<number, {id, score, via}[]>`, `GraphMode`.

- [ ] **Step 1: Create project files**

`frontend/package.json`:

```json
{
  "name": "codetortoise-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "e2e": "playwright test"
  },
  "dependencies": {
    "cytoscape": "^3.34.3",
    "cytoscape-elk": "^2.3.0",
    "diff": "^9.0.0",
    "react": "^19.3.0",
    "react-dom": "^19.3.0",
    "react-router-dom": "^7.18.4"
  },
  "devDependencies": {
    "@playwright/test": "^1.63.0",
    "@types/react": "^19.3.0",
    "@types/react-dom": "^19.3.0",
    "@vitejs/plugin-react": "^6.1.1",
    "typescript": "^5.9.0",
    "vite": "^8.3.1",
    "vitest": "^5.0.2"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`frontend/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../backend/codetortoise/web/static", emptyOutDir: true, chunkSizeWarningLimit: 3000 },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CodeTortoise</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/types.d.ts`:

```ts
declare module "cytoscape-elk" {
  import type { Ext } from "cytoscape";
  const ext: Ext;
  export default ext;
}
```

Then install: `cd frontend && npm install` (commit the generated `package-lock.json`).

- [ ] **Step 2: Write the failing tests**

`frontend/src/lib/diffRows.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { diffRows } from "./diffRows";

describe("diffRows", () => {
  it("numbers old and new lines and marks changes", () => {
    const rows = diffRows("a\nb\nc\n", "a\nB\nc\nd\n");
    expect(rows.map((r) => [r.kind, r.oldNo, r.newNo, r.text])).toEqual([
      ["ctx", 1, 1, "a"], ["del", 2, null, "b"], ["add", null, 2, "B"], ["ctx", 3, 3, "c"], ["add", null, 4, "d"],
    ]);
  });

  it("collapses long unchanged runs", () => {
    const before = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n") + "\n";
    const after = before.replace("l10\n", "L10\n");
    const rows = diffRows(before, after, 2);
    expect(rows[0]).toEqual({ kind: "gap", oldNo: null, newNo: null, text: "8 unchanged line(s)" });
    expect(rows.filter((r) => r.kind !== "gap").map((r) => r.text)).toEqual(["l8", "l9", "l10", "L10", "l11", "l12"]);
    expect(rows[rows.length - 1].text).toBe("7 unchanged line(s)");
  });

  it("handles added and deleted files", () => {
    expect(diffRows("", "x\n").map((r) => r.kind)).toEqual(["add"]);
    expect(diffRows("x\n", "").map((r) => r.kind)).toEqual(["del"]);
  });
});
```

`frontend/src/lib/graph.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Impact } from "../api";
import { blastRings, flowElements } from "./graph";

const impact: Impact = {
  nodes: {
    N1: { id: "N1", key: "a", kind: "function", label: "a", file: null, line: null, status: "changed", layer: 1, confidence: "precise" },
    N2: { id: "N2", key: "b", kind: "function", label: "b", file: null, line: null, status: "unchanged", layer: 0, confidence: "precise" },
    N3: { id: "N3", key: "c", kind: "function", label: "c", file: null, line: null, status: "unchanged", layer: 0, confidence: "heuristic" },
    N4: { id: "N4", key: "field:f", kind: "field", label: "S::f", file: null, line: null, status: "unchanged", layer: null, confidence: "precise" },
  },
  edges: [
    { id: "E1", src: "N1", dst: "N2", kind: "call", status: "unchanged", confidence: "precise", file: null, line: null },
    { id: "E2", src: "N1", dst: "N3", kind: "call", status: "added", confidence: "precise", file: null, line: null },
    { id: "E3", src: "N1", dst: "N4", kind: "writes", status: "added", confidence: "precise", file: null, line: null },
  ],
  changed: ["N1"],
  flows: [{ root: "N1", nodes: ["N1", "N2", "N3"], edges: ["E1", "E2"] }],
  blast: [
    { node: "N2", hop: 1, score: 1, via: "call", path: ["N2", "N1"] },
    { node: "N3", hop: 1, score: 2, via: "data", path: ["N3", "N1"] },
  ],
  fanout: [],
};

describe("flowElements", () => {
  it("diff mode keeps everything with status classes", () => {
    const els = flowElements(impact, ["N1"], "diff", false);
    expect(els.map((e) => e.data.id)).toEqual(["N1", "N2", "N3", "E1", "E2"]);
    expect(els.find((e) => e.data.id === "E2")!.classes).toContain("st-added");
    expect(els.find((e) => e.data.id === "N3")!.classes).toContain("heuristic");
  });

  it("before mode drops added edges and orphaned nodes", () => {
    const els = flowElements(impact, ["N1"], "before", false);
    expect(els.map((e) => e.data.id)).toEqual(["N1", "N2", "E1"]);
  });

  it("data edges are optional", () => {
    const els = flowElements(impact, ["N1"], "after", true);
    expect(els.map((e) => e.data.id)).toContain("E3");
    expect(els.find((e) => e.data.id === "N4")!.classes).toContain("field");
  });
});

describe("blastRings", () => {
  it("groups by hop, highest score first", () => {
    expect([...blastRings(impact).get(1)!.map((x) => x.id)]).toEqual(["N3", "N2"]);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Error: Cannot find module './diffRows'`

- [ ] **Step 4: Implement**

`frontend/src/api.ts`:

```ts
export type Severity = "info" | "low" | "medium" | "high";
export type StageStatus = "pending" | "running" | "ok" | "degraded" | "failed" | "skipped";

export interface Me { user: string; is_owner: boolean; swarm_ready: boolean }
export interface ReviewRow {
  id: number; title: string; created_by: string; created_at: string;
  status: string; risk: "low" | "medium" | "high" | null; cls: number[];
}
export interface Stage { name: string; status: StageStatus; message: string; started_at: string | null; finished_at: string | null }
export interface SwarmInfo { id: number; state: string; state_label?: string; url: string; votes: Record<string, number>; author?: string }
export interface ClRow { review_id: number; cl: number; status: string; user: string | null; description: string | null; swarm: SwarmInfo | null }
export interface ReviewDetail { review: ReviewRow; cls: ClRow[]; stages: Stage[] }

export interface Node {
  id: string; key: string; kind: "function" | "field"; label: string; file: string | null; line: number | null;
  status: "added" | "removed" | "changed" | "unchanged"; layer: number | null; confidence: "precise" | "heuristic";
}
export interface Edge {
  id: string; src: string; dst: string; kind: "call" | "virtual" | "writes" | "reads";
  status: "added" | "removed" | "unchanged"; confidence: "precise" | "may" | "heuristic"; file: string | null; line: number | null;
}
export interface Flow { root: string; nodes: string[]; edges: string[] }
export interface BlastItem { node: string; hop: number; score: number; via: "call" | "data"; path: string[] }
export interface FanOut { header: string; total_tus: number; by_layer: Record<string, number> }
export interface Impact { nodes: Record<string, Node>; edges: Edge[]; changed: string[]; flows: Flow[]; blast: BlastItem[]; fanout: FanOut[] }

export interface Evidence { text: string; file: string | null; line: number | null; severity: Severity }
export interface Cited { text: string; cites: string[]; verified: boolean }
export interface Finding {
  id: string; kind: string; severity: Severity; title: string; nodes: string[]; evidence: Evidence[]; summary: string;
  explanation: string | null; verify_steps: string[]; hypotheses: Cited[]; state: "open" | "ack" | "dismissed";
}
export interface Chapter {
  level: number | null; name: string; narrative: string; cites: string[]; verified: boolean;
  cross_layer_effects: Cited[]; nodes: string[]; findings: string[];
}
export interface Storyboard {
  summary: string; risk: "low" | "medium" | "high"; review_order: string[]; verified: boolean;
  chapters: Chapter[]; llm_used: boolean; llm_error: string | null;
}
export interface Drift { depot: string; local: string; expected: string; actual: string }
export interface StoryboardResponse { storyboard: Storyboard | null; drift: Drift[] }
export interface PerCl { cl: number; before: string; after: string }
export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review";
export interface Comment {
  id: number; review_id: number; parent_id: number | null; author: string; body: string;
  anchor_kind: AnchorKind; anchor: Record<string, unknown>; resolved: boolean; created_at: string; edited_at: string | null;
}
export interface HealthCheck { name: string; ok: boolean; hard: boolean; detail: string }
export interface Health { checks: HealthCheck[]; ready: boolean; index_generation: number; libclang: string | null; strip_flags: string[]; index_building: boolean }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail ?? msg; } catch { /* not json */ }
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => call<Me>("GET", "/api/me"),
  login: (user: string, password: string) => call<{ user: string; is_owner: boolean }>("POST", "/api/login", { user, password }),
  logout: () => call("POST", "/api/logout"),
  health: () => call<Health>("GET", "/api/health"),
  rebuildIndex: () => call("POST", "/api/index/rebuild"),
  reviews: () => call<ReviewRow[]>("GET", "/api/reviews"),
  createReview: (cls: number[], title?: string) => call<ReviewRow>("POST", "/api/reviews", { cls, title }),
  review: (id: number) => call<ReviewDetail>("GET", `/api/reviews/${id}`),
  rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
  storyboard: (id: number) => call<StoryboardResponse>("GET", `/api/reviews/${id}/storyboard`),
  impact: (id: number) => call<Impact | null>("GET", `/api/reviews/${id}/impact`),
  findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`),
  setFindingState: (id: number, fid: string, state: Finding["state"]) =>
    call("PATCH", `/api/reviews/${id}/findings/${fid}`, { state }),
  files: (id: number) => call<FileChange[]>("GET", `/api/reviews/${id}/files`),
  comments: (id: number) => call<Comment[]>("GET", `/api/reviews/${id}/comments`),
  addComment: (id: number, body: string, anchor_kind: AnchorKind, anchor: Record<string, unknown>, parent_id?: number) =>
    call<Comment>("POST", `/api/reviews/${id}/comments`, { body, anchor_kind, anchor, parent_id }),
  patchComment: (cid: number, patch: { body?: string; resolved?: boolean }) => call<Comment>("PATCH", `/api/comments/${cid}`, patch),
  deleteComment: (cid: number) => call("DELETE", `/api/comments/${cid}`),
  swarmRefresh: (id: number, cl: number) => call<SwarmInfo | null>("POST", `/api/reviews/${id}/cls/${cl}/swarm/refresh`),
  swarmCreate: (id: number, cl: number) => call<SwarmInfo>("POST", `/api/reviews/${id}/cls/${cl}/swarm/create`),
  swarmPost: (id: number, cl: number, confirm_repeat = false) =>
    call<{ comment_id: string }>("POST", `/api/reviews/${id}/cls/${cl}/swarm/post`, { confirm_repeat }),
  renameLayer: (level: number, name: string) => call("PUT", `/api/layers/${level}`, { name }),
};
```

`frontend/src/lib/diffRows.ts`:

```ts
import { diffLines } from "diff";

export type RowKind = "ctx" | "add" | "del" | "gap";
export interface Row { kind: RowKind; oldNo: number | null; newNo: number | null; text: string }

function splitLines(value: string): string[] {
  const lines = value.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Unified diff rows with line numbers; unchanged runs longer than 2*context collapse into a "gap" row. */
export function diffRows(before: string, after: string, context = 3): Row[] {
  const rows: Row[] = [];
  let o = 1;
  let n = 1;
  for (const part of diffLines(before, after)) {
    const lines = splitLines(part.value);
    if (part.added) {
      for (const t of lines) rows.push({ kind: "add", oldNo: null, newNo: n++, text: t });
    } else if (part.removed) {
      for (const t of lines) rows.push({ kind: "del", oldNo: o++, newNo: null, text: t });
    } else {
      lines.forEach((t) => rows.push({ kind: "ctx", oldNo: o++, newNo: n++, text: t }));
    }
  }
  const keep = new Array(rows.length).fill(false);
  rows.forEach((r, i) => {
    if (r.kind !== "ctx") for (let j = Math.max(0, i - context); j <= Math.min(rows.length - 1, i + context); j++) keep[j] = true;
  });
  const out: Row[] = [];
  let hidden = 0;
  rows.forEach((r, i) => {
    if (keep[i]) {
      if (hidden) out.push({ kind: "gap", oldNo: null, newNo: null, text: `${hidden} unchanged line(s)` });
      hidden = 0;
      out.push(r);
    } else hidden++;
  });
  if (hidden && out.length) out.push({ kind: "gap", oldNo: null, newNo: null, text: `${hidden} unchanged line(s)` });
  return out;
}
```

`frontend/src/lib/graph.ts`:

```ts
import type { Edge, Impact } from "../api";

export type GraphMode = "before" | "after" | "diff";

export interface GraphElement { data: Record<string, unknown>; classes: string }

/** Nodes/edges of the given flows (or all changed flows) as cytoscape elements, filtered by mode. */
export function flowElements(impact: Impact, roots: string[], mode: GraphMode, showData: boolean): GraphElement[] {
  const edgeById = new Map(impact.edges.map((e) => [e.id, e]));
  const nodeIds = new Set<string>();
  const edges: Edge[] = [];
  for (const flow of impact.flows.filter((f) => roots.includes(f.root))) {
    flow.nodes.forEach((n) => nodeIds.add(n));
    flow.edges.forEach((id) => { const e = edgeById.get(id); if (e) edges.push(e); });
  }
  if (showData) {
    for (const e of impact.edges) {
      if ((e.kind === "writes" || e.kind === "reads") && roots.includes(e.src)) {
        edges.push(e);
        nodeIds.add(e.dst);
      }
    }
  }
  const visible = (e: Edge) => mode === "diff" || (mode === "after" ? e.status !== "removed" : e.status !== "added");
  const kept = [...new Map(edges.filter(visible).map((e) => [e.id, e])).values()];
  const used = new Set<string>(roots);
  kept.forEach((e) => { used.add(e.src); used.add(e.dst); });
  const out: GraphElement[] = [];
  for (const id of nodeIds) {
    if (!used.has(id)) continue;
    const n = impact.nodes[id];
    if (!n) continue;
    const status = mode === "diff" ? n.status : "unchanged";
    out.push({
      data: { id, label: n.label, layer: n.layer ?? -1 },
      classes: [n.kind, `st-${status}`, n.confidence === "heuristic" ? "heuristic" : "", roots.includes(id) ? "root" : ""].join(" ").trim(),
    });
  }
  for (const e of kept) {
    const status = mode === "diff" ? e.status : "unchanged";
    out.push({
      data: { id: e.id, source: e.src, target: e.dst, label: e.kind === "call" ? "" : e.kind },
      classes: [e.kind === "writes" || e.kind === "reads" ? "data" : "call", e.kind, `st-${status}`, `conf-${e.confidence}`].join(" "),
    });
  }
  return out;
}

/** Nodes grouped by blast hop ring, highest score first. */
export function blastRings(impact: Impact): Map<number, { id: string; score: number; via: string }[]> {
  const rings = new Map<number, { id: string; score: number; via: string }[]>();
  for (const b of impact.blast) {
    const ring = rings.get(b.hop) ?? [];
    ring.push({ id: b.node, score: b.score, via: b.via });
    rings.set(b.hop, ring);
  }
  for (const ring of rings.values()) ring.sort((a, b) => b.score - a.score);
  return rings;
}
```

- [ ] **Step 5: Verify**

Run: `cd frontend && npm test`
Expected: `Tests  7 passed (7)`

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src/types.d.ts frontend/src/lib/diffRows.test.ts frontend/src/lib/graph.test.ts frontend/src/api.ts frontend/src/lib/diffRows.ts frontend/src/lib/graph.ts frontend/package-lock.json
git commit -m "feat(frontend): tooling, typed API client, diff and graph helpers"
```

---

### Task 21: Frontend shell: auth, reviews list, new review, health

App shell with a `useMe()` context, redirect to `/login` when the session is missing, top navigation
(owner sees New review / Health), the reviews table, the CL entry form, and the health page (checks, index
rebuild, stripped flags, LLM data notice). Styling uses CSS custom properties with a dark-mode variant.

**Files:**
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/components/Badges.tsx`
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/pages/Reviews.tsx`
- Create: `frontend/src/pages/NewReview.tsx`
- Create: `frontend/src/pages/Health.tsx`

**Interfaces:**
- Consumes: `api`, types from Task 20.
- Produces: `useMe(): Me | null` (from `App.tsx`), `RiskBadge`, `StatusBadge`, `SeverityBadge`, `parseCls(text) -> number[]`.

- [ ] **Step 1: Implement**

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

`frontend/src/App.tsx`:

```tsx
import { createContext, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, type Me } from "./api";
import Health from "./pages/Health";
import Login from "./pages/Login";
import NewReview from "./pages/NewReview";
import Reviews from "./pages/Reviews";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, [location.pathname]);

  if (me === undefined) return <div className="page muted">Loading…</div>;
  if (me === null && location.pathname !== "/login")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;

  return (
    <MeContext.Provider value={me}>
      <header className="topbar">
        <Link to="/" className="brand">CodeTortoise</Link>
        {me && (
          <nav>
            <Link to="/">Reviews</Link>
            {me.is_owner && <Link to="/new">New review</Link>}
            {me.is_owner && <Link to="/health">Health</Link>}
            <span className="muted">{me.user}</span>
            <button className="link" onClick={() => api.logout().then(() => { setMe(null); navigate("/login"); })}>
              Log out
            </button>
          </nav>
        )}
      </header>
      <Routes>
        <Route path="/login" element={<Login onLogin={() => api.me().then(setMe)} />} />
        <Route path="/" element={<Reviews />} />
        <Route path="/new" element={<NewReview />} />
        <Route path="/health" element={<Health />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MeContext.Provider>
  );
}
```

`frontend/src/styles.css`:

```css
:root {
  --bg: #faf9f6; --surface: #ffffff; --ink: #1d1b16; --muted: #6b665b; --line: #e3dfd6; --accent: #2451b8;
  --ok: #2f7d32; --warn: #a07a10; --bad: #b3261e; --info: #55606e;
  --add-bg: #e7f5e7; --del-bg: #fbe9e8; --gap-bg: #f1efe9;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17161a; --surface: #201f24; --ink: #ece9e2; --muted: #a29d92; --line: #34323a; --accent: #8fb0ff;
    --ok: #7bc47f; --warn: #e0b64c; --bad: #f08a82; --info: #9aa6b5;
    --add-bg: #1e3321; --del-bg: #3a2020; --gap-bg: #26252b;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(--sans); }
a, .link { color: var(--accent); }
button { font: inherit; cursor: pointer; border: 1px solid var(--line); background: var(--surface); color: var(--ink);
  border-radius: 6px; padding: 5px 12px; }
button:disabled { opacity: .5; cursor: default; }
button.link { border: 0; background: none; padding: 0 4px; text-decoration: underline; text-underline-offset: 2px; }
input, textarea, select { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 8px; width: 100%; }
select[multiple] { min-width: 220px; height: 5.5em; }
h1 { font-size: 22px; margin: 0 0 12px; } h2 { font-size: 16px; margin: 0; } h3 { font-size: 14px; margin: 12px 0 4px; }
h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 12px 0 4px; }
.mono { font-family: var(--mono); } .small { font-size: 12px; } .muted { color: var(--muted); }
.error { color: var(--bad); }
.topbar { display: flex; align-items: center; gap: 24px; padding: 10px 24px; border-bottom: 1px solid var(--line); background: var(--surface); }
.topbar nav { display: flex; gap: 16px; align-items: center; margin-left: auto; }
.brand { font-weight: 700; text-decoration: none; color: var(--ink); letter-spacing: .01em; }
.page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.page.narrow { max-width: 480px; } .page.wide { max-width: none; }
.stack { display: flex; flex-direction: column; gap: 12px; } .stack label { display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; margin: 12px 0; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
.table th { font-size: 12px; color: var(--muted); font-weight: 600; }
.badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px;
  border: 1px solid currentColor; color: var(--info); text-transform: lowercase; }
.badge.ok { color: var(--ok); } .badge.degraded, .badge.running, .badge.queued { color: var(--warn); } .badge.failed { color: var(--bad); }
.badge.risk-high, .badge.sev-high { color: var(--bad); } .badge.risk-medium, .badge.sev-medium { color: var(--warn); }
.badge.risk-low, .badge.sev-low { color: var(--ok); } .badge.via-data { color: #9b6a2f; }
.banner { border-radius: 8px; padding: 8px 12px; margin: 8px 0; background: var(--gap-bg); }
.banner.warn { border-left: 4px solid var(--warn); } .banner.error { border-left: 4px solid var(--bad); }
.review-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.review-head h1 { margin: 0; }
.stages { display: flex; gap: 14px; list-style: none; padding: 0; margin: 12px 0; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.stage .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--line); margin-right: 5px; }
.stage.ok .dot { background: var(--ok); } .stage.degraded .dot { background: var(--warn); } .stage.failed .dot { background: var(--bad); }
.stage.running .dot { background: var(--accent); animation: pulse 1s infinite alternate; } .stage.skipped { text-decoration: line-through; }
@keyframes pulse { from { opacity: .3; } to { opacity: 1; } }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin: 12px 0 16px; }
.tabs a { padding: 8px 14px; text-decoration: none; color: var(--muted); border-bottom: 2px solid transparent; }
.tabs a.on { color: var(--ink); border-color: var(--accent); }
.cite { font: 11px var(--mono); padding: 0 5px; margin: 0 1px; border-radius: 4px; color: var(--accent); }
.cites { white-space: nowrap; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; list-style: none; padding: 0; }
.chip { font-family: var(--mono); font-size: 12px; }
.chip.st-changed { border-color: var(--warn); } .chip.st-added { border-color: var(--ok); } .chip.st-removed { border-color: var(--bad); }
.findings-mini { list-style: none; padding: 0; } .findings-mini li { margin: 4px 0; }
.finding.dismissed { opacity: .55; } .finding.focus { outline: 2px solid var(--accent); }
.finding h3 { margin: 0; } .finding .actions { margin-left: auto; }
.evidence li.sev-high { color: var(--bad); } .evidence li.sev-medium { color: var(--warn); }
.toolbar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.toolbar label { display: flex; gap: 6px; align-items: center; } .toolbar select:not([multiple]) { width: auto; }
.toolbar input[type=checkbox] { width: auto; }
.seg { display: inline-flex; } .seg button { border-radius: 0; } .seg button:first-child { border-radius: 6px 0 0 6px; }
.seg button:last-child { border-radius: 0 6px 6px 0; } .seg button.on { background: var(--accent); color: var(--surface); border-color: var(--accent); }
.flows-body { display: grid; grid-template-columns: 1fr 340px; gap: 12px; }
.graph { height: 68vh; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.side { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 12px; overflow: auto; max-height: 68vh; }
.side ul { padding-left: 16px; }
.bar { height: 8px; background: var(--gap-bg); border-radius: 4px; overflow: hidden; } .bar div { height: 100%; background: var(--warn); }
.file summary { cursor: pointer; }
.diff { width: 100%; border-collapse: collapse; font: 12px/1.45 var(--mono); margin-top: 8px; }
.diff td { padding: 0 6px; white-space: pre-wrap; word-break: break-all; }
.diff .ln { width: 1%; color: var(--muted); text-align: right; user-select: none; }
.diff .add-comment { width: 1%; } .diff .add-comment button { visibility: hidden; font-weight: 700; }
.diff tr:hover .add-comment button { visibility: visible; }
.diff tr.add { background: var(--add-bg); } .diff tr.del { background: var(--del-bg); }
.diff tr.gap td { background: var(--gap-bg); color: var(--muted); text-align: center; }
.diff .sign { color: var(--muted); margin-right: 6px; }
.diff .comment-row td { font-family: var(--sans); padding: 6px 0; }
.comments { margin-top: 8px; } .thread { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin: 6px 0; background: var(--bg); }
.thread.resolved { opacity: .6; } .comment + .comment { border-top: 1px dashed var(--line); margin-top: 6px; padding-top: 6px; }
.comment-head { display: flex; gap: 8px; align-items: baseline; } .comment-body { white-space: pre-wrap; }
.thread-actions { display: flex; gap: 8px; align-items: flex-start; margin-top: 6px; }
.composer { display: flex; gap: 8px; align-items: flex-start; margin-top: 6px; flex: 1; } .composer textarea { flex: 1; }
@media (max-width: 860px) { .flows-body { grid-template-columns: 1fr; } .page { padding: 16px; } }
```

`frontend/src/components/Badges.tsx`:

```tsx
export function RiskBadge({ risk }: { risk: string | null }) {
  if (!risk) return <span className="muted">—</span>;
  return <span className={`badge risk-${risk}`}>{risk}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const cls = status === "done" ? "ok" : status;
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge sev-${severity}`}>{severity}</span>;
}
```

`frontend/src/pages/Login.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

export default function Login({ onLogin }: { onLogin: () => Promise<unknown> }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(user.trim(), password);
      await onLogin();
      navigate(params.get("next") || "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page narrow">
      <h1>Sign in</h1>
      <p className="muted">Use your Perforce credentials.</p>
      <form onSubmit={submit} className="stack">
        <label>P4 user<input autoFocus value={user} onChange={(e) => setUser(e.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button disabled={busy || !user.trim()}>{busy ? "Checking…" : "Sign in"}</button>
      </form>
    </main>
  );
}
```

`frontend/src/pages/Reviews.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ReviewRow } from "../api";
import { RiskBadge, StatusBadge } from "../components/Badges";

export default function Reviews() {
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.reviews().then(setRows).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <main className="page error">{error}</main>;
  if (!rows) return <main className="page muted">Loading…</main>;
  return (
    <main className="page">
      <h1>Reviews</h1>
      {rows.length === 0 ? (
        <p className="muted">No reviews yet.</p>
      ) : (
        <table className="table">
          <thead><tr><th>#</th><th>Title</th><th>CLs</th><th>Status</th><th>Risk</th><th>Created</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td><Link to={`/r/${r.id}`}>{r.title}</Link></td>
                <td className="mono">{r.cls.join(", ")}</td>
                <td><StatusBadge status={r.status} /></td>
                <td><RiskBadge risk={r.risk} /></td>
                <td className="muted">{r.created_at.replace("T", " ").slice(0, 16)} · {r.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
```

`frontend/src/pages/NewReview.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export function parseCls(text: string): number[] {
  return [...new Set(text.split(/[\s,]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n > 0))];
}

export default function NewReview() {
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const cls = parseCls(text);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api.createReview(cls, title.trim() || undefined);
      navigate(`/r/${r.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="page narrow">
      <h1>New review</h1>
      <form onSubmit={submit} className="stack">
        <label>
          Changelists (shelved or submitted)
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="12345 12346 12350" />
        </label>
        <div className="muted">{cls.length ? `Will analyse: ${cls.join(", ")}` : "Enter one or more CL numbers."}</div>
        <label>Title (optional)<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button disabled={!cls.length}>Start review</button>
      </form>
    </main>
  );
}
```

`frontend/src/pages/Health.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api, type Health as HealthT } from "../api";

export default function Health() {
  const [h, setH] = useState<HealthT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.health().then(setH).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => { load(); }, []);

  if (error) return <main className="page error">{error}</main>;
  if (!h) return <main className="page muted">Checking…</main>;
  return (
    <main className="page">
      <h1>Health {h.ready ? <span className="badge ok">ready</span> : <span className="badge failed">not ready</span>}</h1>
      <table className="table">
        <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
        <tbody>
          {h.checks.map((c) => (
            <tr key={c.name}>
              <td>{c.name}{c.hard ? "" : <span className="muted"> (warning only)</span>}</td>
              <td><span className={`badge ${c.ok ? "ok" : c.hard ? "failed" : "degraded"}`}>{c.ok ? "ok" : "fail"}</span></td>
              <td className="mono small">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <section className="card">
        <h2>Symbol index</h2>
        <p>Generation {h.index_generation}{h.index_building ? " — rebuilding…" : ""}</p>
        <button onClick={() => api.rebuildIndex().then(load)}>Rebuild index</button>
      </section>
      <section className="card">
        <h2>Flags stripped for libclang</h2>
        <p className="mono small">{h.strip_flags.length ? h.strip_flags.join(" ") : "none"}</p>
      </section>
      <p className="muted small">Code snippets of changed functions and their callers are sent to the configured LLM endpoint.</p>
    </main>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run build`
Expected: `tsc --noEmit` passes and Vite prints `✓ built in …`, writing `backend/codetortoise/web/static/index.html`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/main.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/components/Badges.tsx frontend/src/pages/Login.tsx frontend/src/pages/Reviews.tsx frontend/src/pages/NewReview.tsx frontend/src/pages/Health.tsx
git commit -m "feat(frontend): app shell, login, reviews, new review and health pages"
```

---

### Task 22: Review page: storyboard, call flows, blast radius, findings, files, CLs & Swarm

The review page subscribes to `/events` until the pipeline is terminal, then loads all results.
Tabs:
- **Storyboard** — drift banner, summary with risk and review order, layer chapters top-down with cite chips
  (N…/F…) that jump to the graph or the finding.
- **Call flows** — cytoscape + ELK layered layout, compound nodes as layer bands, before/after/diff toggle, field data
  edges, node side panel with callers/callees, findings and function comments.
- **Blast radius** — rings by hop, score bars, via/layer/confidence filters, header fan-out table.
- **Findings** — evidence, LLM explanation/verify steps/grounded hypotheses, owner ack/dismiss, comments.
- **Files** — cumulative or per-CL unified diffs with per-line threads.
- **CLs & Swarm** — Swarm link, state and votes; owner refresh / create review / post summary link.

**Files:**
- Create: `frontend/src/components/CiteText.tsx`
- Create: `frontend/src/components/Comments.tsx`
- Create: `frontend/src/components/Stages.tsx`
- Create: `frontend/src/components/Storyboard.tsx`
- Create: `frontend/src/components/Findings.tsx`
- Create: `frontend/src/components/CallFlows.tsx`
- Create: `frontend/src/components/BlastRadius.tsx`
- Create: `frontend/src/components/DiffView.tsx`
- Create: `frontend/src/components/Files.tsx`
- Create: `frontend/src/components/ClsPanel.tsx`
- Create: `frontend/src/pages/Review.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: everything from Tasks 20–21.
- Produces: route `/r/:id/*` with sub-routes `storyboard | flows | blast | findings | files | cls`.
- Comment anchors: `review {}`, `chapter {level}`, `finding {kind, title}` (stable across re-runs), `function {key}`,
  `line {depot, cl, side, line}`.

- [ ] **Step 1: Implement**

`frontend/src/components/CiteText.tsx`:

```tsx
import { Fragment } from "react";

/** Renders text, turning node ids (N12) and finding ids (F3) into clickable chips. */
export default function CiteText({ text, onCite }: { text: string; onCite: (id: string) => void }) {
  const parts = text.split(/\b([NF]\d+)\b/);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <button key={i} className="cite" onClick={() => onCite(p)}>{p}</button>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

export function CiteList({ ids, onCite }: { ids: string[]; onCite: (id: string) => void }) {
  if (!ids.length) return null;
  return (
    <span className="cites">
      {ids.map((id) => <button key={id} className="cite" onClick={() => onCite(id)}>{id}</button>)}
    </span>
  );
}
```

`frontend/src/components/Comments.tsx`:

```tsx
import { useState } from "react";
import { api, type AnchorKind, type Comment } from "../api";
import { useMe } from "../App";

export function anchorMatches(c: Comment, kind: AnchorKind, anchor: Record<string, unknown>): boolean {
  return c.anchor_kind === kind && Object.entries(anchor).every(([k, v]) => c.anchor[k] === v);
}

interface Props {
  reviewId: number;
  comments: Comment[];
  kind: AnchorKind;
  anchor: Record<string, unknown>;
  onChange: () => void;
  compact?: boolean;
}

/** All threads for one anchor plus a composer. */
export default function Comments({ reviewId, comments, kind, anchor, onChange, compact }: Props) {
  const roots = comments.filter((c) => c.parent_id === null && anchorMatches(c, kind, anchor));
  const [open, setOpen] = useState(!compact || roots.length > 0);
  if (!open)
    return <button className="link small" onClick={() => setOpen(true)}>+ comment</button>;
  return (
    <div className="comments">
      {roots.map((root) => (
        <Thread key={root.id} root={root} replies={comments.filter((c) => c.parent_id === root.id)}
                reviewId={reviewId} onChange={onChange} />
      ))}
      <Composer onSubmit={(body) => api.addComment(reviewId, body, kind, anchor).then(onChange)}
                placeholder={roots.length ? "Start another thread…" : "Leave a comment…"} />
    </div>
  );
}

function Thread({ root, replies, reviewId, onChange }: { root: Comment; replies: Comment[]; reviewId: number; onChange: () => void }) {
  return (
    <div className={`thread ${root.resolved ? "resolved" : ""}`}>
      {[root, ...replies].map((c) => <CommentView key={c.id} c={c} onChange={onChange} />)}
      <div className="thread-actions">
        <Composer small placeholder="Reply…"
                  onSubmit={(body) => api.addComment(reviewId, body, root.anchor_kind, root.anchor, root.id).then(onChange)} />
        <button className="link small" onClick={() => api.patchComment(root.id, { resolved: !root.resolved }).then(onChange)}>
          {root.resolved ? "Reopen" : "Resolve"}
        </button>
      </div>
    </div>
  );
}

function CommentView({ c, onChange }: { c: Comment; onChange: () => void }) {
  const me = useMe();
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(c.body);
  const mine = me?.user === c.author;
  return (
    <div className="comment">
      <div className="comment-head">
        <strong>{c.author}</strong>
        <span className="muted small">{c.created_at.replace("T", " ").slice(0, 16)}{c.edited_at ? " (edited)" : ""}</span>
        {mine && !editing && <button className="link small" onClick={() => setEditing(true)}>edit</button>}
        {(mine || me?.is_owner) && (
          <button className="link small" onClick={() => api.deleteComment(c.id).then(onChange)}>delete</button>
        )}
      </div>
      {editing ? (
        <div className="stack">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} />
          <div>
            <button onClick={() => api.patchComment(c.id, { body }).then(() => { setEditing(false); onChange(); })}>Save</button>
            <button className="link" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="comment-body">{c.body}</div>
      )}
    </div>
  );
}

function Composer({ onSubmit, placeholder, small }: { onSubmit: (body: string) => Promise<unknown>; placeholder: string; small?: boolean }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form className={`composer ${small ? "small" : ""}`} onSubmit={(e) => {
      e.preventDefault();
      if (!body.trim()) return;
      setBusy(true);
      onSubmit(body.trim()).then(() => setBody("")).finally(() => setBusy(false));
    }}>
      <textarea rows={small ? 1 : 2} value={body} placeholder={placeholder} onChange={(e) => setBody(e.target.value)} />
      <button disabled={busy || !body.trim()}>{small ? "Reply" : "Comment"}</button>
    </form>
  );
}
```

`frontend/src/components/Stages.tsx`:

```tsx
import type { Stage } from "../api";

export default function Stages({ stages }: { stages: Stage[] }) {
  return (
    <ol className="stages">
      {stages.map((s) => (
        <li key={s.name} className={`stage ${s.status}`} title={s.message || s.status}>
          <span className="dot" />
          {s.name.replace("_", " ")}
        </li>
      ))}
    </ol>
  );
}
```

`frontend/src/components/Storyboard.tsx`:

```tsx
import { api, type Comment, type Drift, type Finding, type Impact, type Storyboard as SB } from "../api";
import { useMe } from "../App";
import { RiskBadge, SeverityBadge } from "./Badges";
import CiteText, { CiteList } from "./CiteText";
import Comments from "./Comments";

interface Props {
  reviewId: number;
  sb: SB;
  drift: Drift[];
  impact: Impact | null;
  findings: Finding[];
  comments: Comment[];
  onComments: () => void;
  onCite: (id: string) => void;
  onRenamed: () => void;
}

export default function Storyboard({ reviewId, sb, drift, impact, findings, comments, onComments, onCite, onRenamed }: Props) {
  const me = useMe();
  const rename = (level: number, current: string) => {
    const name = prompt("Layer name (applies to all reviews)", current);
    if (name && name.trim()) api.renameLayer(level, name.trim()).then(onRenamed);
  };
  const byId = new Map(findings.map((f) => [f.id, f]));
  const label = (id: string) => impact?.nodes[id]?.label ?? id;
  return (
    <div className="storyboard">
      {drift.length > 0 && (
        <div className="banner warn">
          <strong>Workspace drift:</strong> {drift.length} file(s) in the base workspace are not at the CL base revision;
          surrounding code is analysed at the workspace revision.
          <ul>{drift.map((d) => <li key={d.depot} className="mono small">{d.depot}: expected {d.expected}, have {d.actual}</li>)}</ul>
        </div>
      )}
      <section className="card summary">
        <div className="row">
          <h2>Summary</h2>
          <RiskBadge risk={sb.risk} />
          {!sb.llm_used && <span className="badge degraded" title={sb.llm_error ?? "no LLM configured"}>deterministic</span>}
          {sb.llm_used && !sb.verified && <span className="badge degraded">unverified</span>}
        </div>
        <p><CiteText text={sb.summary} onCite={onCite} /></p>
        {sb.review_order.length > 0 && (
          <div className="small">
            Suggested review order:{" "}
            {sb.review_order.map((id, i) => (
              <span key={id}>{i > 0 && " → "}<button className="cite" onClick={() => onCite(id)}>{label(id)}</button></span>
            ))}
          </div>
        )}
        <Comments reviewId={reviewId} comments={comments} kind="review" anchor={{}} onChange={onComments} compact />
      </section>
      {[...sb.chapters].reverse().map((ch) => (
        <section key={String(ch.level)} className="card chapter">
          <div className="row">
            <h2>{ch.name}</h2>
            {me?.is_owner && ch.level !== null && (
              <button className="link small" onClick={() => rename(ch.level!, ch.name)}>rename</button>
            )}
            {sb.llm_used && !ch.verified && <span className="badge degraded">unverified</span>}
          </div>
          <p><CiteText text={ch.narrative} onCite={onCite} /> <CiteList ids={ch.cites.filter((c) => !ch.narrative.includes(c))} onCite={onCite} /></p>
          {ch.cross_layer_effects.length > 0 && (
            <>
              <h3>Cross-layer effects</h3>
              <ul>{ch.cross_layer_effects.map((c, i) => (
                <li key={i}><CiteText text={c.text} onCite={onCite} /> <CiteList ids={c.cites} onCite={onCite} /></li>
              ))}</ul>
            </>
          )}
          {ch.nodes.length > 0 && (
            <>
              <h3>Changed functions</h3>
              <ul className="chips">
                {ch.nodes.map((n) => (
                  <li key={n}><button className={`chip st-${impact?.nodes[n]?.status}`} onClick={() => onCite(n)}>{label(n)}</button></li>
                ))}
              </ul>
            </>
          )}
          {ch.findings.length > 0 && (
            <>
              <h3>Findings</h3>
              <ul className="findings-mini">
                {ch.findings.map((fid) => byId.get(fid)).filter(Boolean).map((f) => (
                  <li key={f!.id}>
                    <SeverityBadge severity={f!.severity} />{" "}
                    <button className="link" onClick={() => onCite(f!.id)}>{f!.id}: {f!.title}</button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <Comments reviewId={reviewId} comments={comments} kind="chapter" anchor={{ level: ch.level }} onChange={onComments} compact />
        </section>
      ))}
      <p className="muted small">Chapters run from the highest layer (top) to the lowest.</p>
    </div>
  );
}
```

`frontend/src/components/Findings.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { api, type Comment, type Finding } from "../api";
import { useMe } from "../App";
import { SeverityBadge } from "./Badges";
import CiteText, { CiteList } from "./CiteText";
import Comments from "./Comments";

interface Props {
  reviewId: number;
  findings: Finding[];
  focus: string | null;
  comments: Comment[];
  onComments: () => void;
  onFindings: () => void;
  onCite: (id: string) => void;
}

export default function Findings({ reviewId, findings, focus, comments, onComments, onFindings, onCite }: Props) {
  const me = useMe();
  const refs = useRef(new Map<string, HTMLElement>());
  useEffect(() => {
    if (focus) refs.current.get(focus)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus]);
  if (!findings.length) return <p className="muted">No findings.</p>;
  return (
    <div className="findings">
      {findings.map((f) => (
        <section key={f.id} ref={(el) => { if (el) refs.current.set(f.id, el); }}
                 className={`card finding ${f.state} ${focus === f.id ? "focus" : ""}`}>
          <div className="row">
            <SeverityBadge severity={f.severity} />
            <h3>{f.id}: {f.title}</h3>
            <span className="muted small">{f.kind}</span>
            {f.state !== "open" && <span className="badge">{f.state}</span>}
            {me?.is_owner && (
              <span className="actions">
                {(["open", "ack", "dismissed"] as const).filter((s) => s !== f.state).map((s) => (
                  <button key={s} className="link small" onClick={() => api.setFindingState(reviewId, f.id, s).then(onFindings)}>{s}</button>
                ))}
              </span>
            )}
          </div>
          <p>{f.summary} <CiteList ids={f.nodes} onCite={onCite} /></p>
          <h4>Evidence (static analysis)</h4>
          <ul className="evidence">
            {f.evidence.map((e, i) => (
              <li key={i} className={`sev-${e.severity}`}>
                {e.text}
                {e.file && <span className="mono small muted"> {e.file.split("/").slice(-2).join("/")}{e.line ? `:${e.line}` : ""}</span>}
              </li>
            ))}
          </ul>
          {f.explanation && (
            <>
              <h4>Explanation (LLM)</h4>
              <p><CiteText text={f.explanation} onCite={onCite} /></p>
            </>
          )}
          {f.verify_steps.length > 0 && (
            <>
              <h4>Verify</h4>
              <ol>{f.verify_steps.map((s, i) => <li key={i}><CiteText text={s} onCite={onCite} /></li>)}</ol>
            </>
          )}
          {f.hypotheses.length > 0 && (
            <>
              <h4>Possible side effects (LLM, grounded)</h4>
              <ul>{f.hypotheses.map((h, i) => (
                <li key={i}><CiteText text={h.text} onCite={onCite} /> <CiteList ids={h.cites} onCite={onCite} /></li>
              ))}</ul>
            </>
          )}
          <Comments reviewId={reviewId} comments={comments} kind="finding" anchor={{ kind: f.kind, title: f.title }} onChange={onComments} compact />
        </section>
      ))}
    </div>
  );
}
```

`frontend/src/components/CallFlows.tsx`:

```tsx
import cytoscape, { type Core } from "cytoscape";
import elk from "cytoscape-elk";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Comment, Finding, Impact } from "../api";
import { flowElements, type GraphMode } from "../lib/graph";
import { SeverityBadge } from "./Badges";
import Comments from "./Comments";

cytoscape.use(elk);

const STYLE: cytoscape.StylesheetJson = [
  { selector: "node", style: { label: "data(label)", "font-size": 11, "text-valign": "center", "text-halign": "center",
    shape: "round-rectangle", width: "label", height: 26, padding: "8px", "background-color": "#e8e6e1",
    "border-width": 1, "border-color": "#8a8578", color: "#1d1b16" } },
  { selector: "node.field", style: { shape: "tag", "background-color": "#efe7d6", "font-style": "italic" } },
  { selector: "node.layer", style: { label: "data(label)", "text-valign": "top", "text-halign": "center", "font-size": 10,
    color: "#6b665b", "background-opacity": 0.35, "background-color": "#f4f2ee", "border-style": "dashed", "border-color": "#c9c4b8" } },
  { selector: "node.root", style: { "border-width": 3 } },
  { selector: "node.heuristic", style: { "border-style": "dotted" } },
  { selector: "node.st-changed", style: { "background-color": "#f6d98a", "border-color": "#a07a10" } },
  { selector: "node.st-added", style: { "background-color": "#b9e3b9", "border-color": "#2f7d32" } },
  { selector: "node.st-removed", style: { "background-color": "#f2b8b5", "border-color": "#b3261e" } },
  { selector: "node:selected", style: { "border-color": "#2451b8", "border-width": 3 } },
  { selector: "edge", style: { width: 1.5, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#8a8578",
    "target-arrow-color": "#8a8578", label: "data(label)", "font-size": 9, color: "#6b665b" } },
  { selector: "edge.conf-heuristic", style: { "line-style": "dotted" } },
  { selector: "edge.conf-may", style: { "line-style": "dotted", width: 1 } },
  { selector: "edge.data", style: { "line-style": "dashed", "line-color": "#9b6a2f", "target-arrow-color": "#9b6a2f" } },
  { selector: "edge.virtual", style: { "target-arrow-shape": "triangle-tee" } },
  { selector: "edge.st-added", style: { "line-color": "#2f7d32", "target-arrow-color": "#2f7d32", width: 2.5 } },
  { selector: "edge.st-removed", style: { "line-color": "#b3261e", "target-arrow-color": "#b3261e", width: 2.5 } },
];

interface Props {
  reviewId: number;
  impact: Impact;
  findings: Finding[];
  comments: Comment[];
  onComments: () => void;
  focus: string | null;
  onCite: (id: string) => void;
  layerName: (level: number | null) => string;
}

export default function CallFlows({ reviewId, impact, findings, comments, onComments, focus, onCite, layerName }: Props) {
  const [roots, setRoots] = useState<string[]>(impact.changed);
  const [mode, setMode] = useState<GraphMode>("diff");
  const [showData, setShowData] = useState(true);
  const [selected, setSelected] = useState<string | null>(focus);
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);

  useEffect(() => {
    if (focus && impact.changed.includes(focus)) setRoots([focus]);
    if (focus) setSelected(focus);
  }, [focus, impact.changed]);

  const elements = useMemo(() => {
    const els = flowElements(impact, roots, mode, showData);
    const layers = new Set<number>();
    for (const el of els) {
      const layer = el.data.layer as number | undefined;
      if (layer !== undefined && layer >= 0 && !el.data.source) {
        el.data.parent = `layer-${layer}`;
        layers.add(layer);
      }
    }
    const parents = [...layers].map((l) => ({ data: { id: `layer-${l}`, label: layerName(l) }, classes: "layer" }));
    return [...parents, ...els];
  }, [impact, roots, mode, showData, layerName]);

  useEffect(() => {
    if (!box.current) return;
    const inst = cytoscape({ container: box.current, elements, style: STYLE, wheelSensitivity: 0.3 });
    inst.layout({ name: "elk", elk: { algorithm: "layered", "elk.direction": "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN", "elk.layered.spacing.nodeNodeBetweenLayers": 40 } } as cytoscape.LayoutOptions).run();
    inst.on("tap", "node", (e) => { if (!e.target.hasClass("layer")) setSelected(e.target.id()); });
    cy.current = inst;
    return () => inst.destroy();
  }, [elements]);

  useEffect(() => {
    if (!cy.current || !selected) return;
    cy.current.$(":selected").unselect();
    cy.current.$id(selected).select();
  }, [selected, elements]);

  const node = selected ? impact.nodes[selected] : null;
  const related = findings.filter((f) => selected && f.nodes.includes(selected));
  const incoming = impact.edges.filter((e) => e.dst === selected);
  const outgoing = impact.edges.filter((e) => e.src === selected);

  return (
    <div className="flows">
      <div className="toolbar">
        <label>Flow roots{" "}
          <select multiple value={roots} onChange={(e) => setRoots([...e.target.selectedOptions].map((o) => o.value))}>
            {impact.changed.map((id) => <option key={id} value={id}>{impact.nodes[id].label}</option>)}
          </select>
        </label>
        <div className="seg">
          {(["before", "after", "diff"] as const).map((m) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>{m}</button>
          ))}
        </div>
        <label><input type="checkbox" checked={showData} onChange={(e) => setShowData(e.target.checked)} /> field writes/reads</label>
        <span className="legend small muted">solid = call (clang) · dotted = heuristic/may · dashed = field data · ⊣ virtual</span>
      </div>
      <div className="flows-body">
        <div ref={box} className="graph" data-testid="flow-graph" />
        <aside className="side">
          {!node ? <p className="muted">Select a node.</p> : (
            <>
              <h3>{node.label}</h3>
              <p className="small muted">{node.kind} · {node.status} · {layerName(node.layer)} · {node.confidence}</p>
              {node.file && <p className="mono small">{node.file}{node.line ? `:${node.line}` : ""}</p>}
              {related.length > 0 && (
                <>
                  <h4>Findings</h4>
                  <ul>{related.map((f) => (
                    <li key={f.id}><SeverityBadge severity={f.severity} /> <button className="link" onClick={() => onCite(f.id)}>{f.id}: {f.title}</button></li>
                  ))}</ul>
                </>
              )}
              <h4>Callers / users ({incoming.length})</h4>
              <ul className="small">{incoming.slice(0, 30).map((e) => (
                <li key={e.id}><button className="link" onClick={() => setSelected(e.src)}>{impact.nodes[e.src].label}</button> <span className="muted">{e.kind} · {e.status} · {e.confidence}</span></li>
              ))}</ul>
              <h4>Calls / touches ({outgoing.length})</h4>
              <ul className="small">{outgoing.slice(0, 30).map((e) => (
                <li key={e.id}><button className="link" onClick={() => setSelected(e.dst)}>{impact.nodes[e.dst].label}</button> <span className="muted">{e.kind} · {e.status} · {e.confidence}</span></li>
              ))}</ul>
              <Comments reviewId={reviewId} comments={comments} kind="function" anchor={{ key: node.key }} onChange={onComments} compact />
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
```

`frontend/src/components/BlastRadius.tsx`:

```tsx
import { useMemo, useState } from "react";
import type { Impact } from "../api";
import { blastRings } from "../lib/graph";

interface Props { impact: Impact; onCite: (id: string) => void; layerName: (level: number | null) => string }

export default function BlastRadius({ impact, onCite, layerName }: Props) {
  const [via, setVia] = useState<"all" | "call" | "data">("all");
  const [layer, setLayer] = useState<string>("all");
  const [conf, setConf] = useState<"all" | "precise">("all");
  const layers = [...new Set(impact.blast.map((b) => impact.nodes[b.node].layer))];
  const filtered = useMemo(() => ({
    ...impact,
    blast: impact.blast.filter((b) => {
      const n = impact.nodes[b.node];
      return (via === "all" || b.via === via) && (layer === "all" || String(n.layer) === layer)
        && (conf === "all" || n.confidence === "precise");
    }),
  }), [impact, via, layer, conf]);
  const rings = blastRings(filtered);
  const max = Math.max(1, ...impact.blast.map((b) => b.score));

  return (
    <div className="blast">
      <div className="toolbar">
        <label>Via <select value={via} onChange={(e) => setVia(e.target.value as typeof via)}>
          <option value="all">call + data</option><option value="call">call</option><option value="data">field data</option>
        </select></label>
        <label>Layer <select value={layer} onChange={(e) => setLayer(e.target.value)}>
          <option value="all">all</option>
          {layers.map((l) => <option key={String(l)} value={String(l)}>{layerName(l)}</option>)}
        </select></label>
        <label>Confidence <select value={conf} onChange={(e) => setConf(e.target.value as typeof conf)}>
          <option value="all">all</option><option value="precise">precise nodes only</option>
        </select></label>
      </div>
      <p className="small muted">
        Seeds: {impact.changed.map((id) => impact.nodes[id].label).join(", ")}. Score = Σ(edge confidence / hop),
        boosted for cross-layer callers, entry points and virtual dispatch.
      </p>
      {[...rings.keys()].sort((a, b) => a - b).map((hop) => (
        <section key={hop} className="card ring">
          <h3>Hop {hop}</h3>
          <table className="table">
            <tbody>
              {rings.get(hop)!.map((r) => {
                const n = impact.nodes[r.id];
                const item = impact.blast.find((b) => b.node === r.id)!;
                return (
                  <tr key={r.id}>
                    <td style={{ width: "30%" }}><button className="link" onClick={() => onCite(r.id)}>{n.label}</button></td>
                    <td style={{ width: 140 }}><div className="bar"><div style={{ width: `${(100 * r.score) / max}%` }} /></div></td>
                    <td className="mono small">{r.score}</td>
                    <td><span className={`badge via-${r.via}`}>{r.via}</span></td>
                    <td className="small muted">{layerName(n.layer)} · {n.confidence}</td>
                    <td className="small muted">{item.path.map((p) => impact.nodes[p].label).join(" → ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
      {impact.fanout.length > 0 && (
        <section className="card">
          <h3>Header fan-out</h3>
          <table className="table">
            <thead><tr><th>Header</th><th>TUs</th><th>By layer</th></tr></thead>
            <tbody>{impact.fanout.map((f) => (
              <tr key={f.header}>
                <td className="mono small">{f.header}</td><td>{f.total_tus}</td>
                <td className="small">{Object.entries(f.by_layer).map(([k, v]) => `${k}: ${v}`).join(" · ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      )}
    </div>
  );
}
```

`frontend/src/components/DiffView.tsx`:

```tsx
import { Fragment, useState } from "react";
import type { Comment } from "../api";
import { diffRows } from "../lib/diffRows";
import Comments, { anchorMatches } from "./Comments";

interface Props {
  reviewId: number;
  depot: string;
  cl: number | null;
  before: string;
  after: string;
  comments: Comment[];
  onComments: () => void;
}

/** Unified diff with per-line comment threads (anchored to new line numbers, or old ones for deletions). */
export default function DiffView({ reviewId, depot, cl, before, after, comments, onComments }: Props) {
  const rows = diffRows(before, after);
  const [openAt, setOpenAt] = useState<string | null>(null);
  return (
    <table className="diff">
      <tbody>
        {rows.map((r, i) => {
          if (r.kind === "gap") return <tr key={i} className="gap"><td colSpan={4}>⋯ {r.text}</td></tr>;
          const side = r.newNo !== null ? "new" : "old";
          const line = r.newNo ?? r.oldNo;
          const anchor = { depot, cl, side, line };
          const key = `${side}:${line}`;
          const has = comments.some((c) => c.parent_id === null && anchorMatches(c, "line", anchor));
          return (
            <Fragment key={i}>
              <tr className={r.kind}>
                <td className="ln">{r.oldNo ?? ""}</td>
                <td className="ln">{r.newNo ?? ""}</td>
                <td className="add-comment"><button className="link" title="Comment on this line" onClick={() => setOpenAt(openAt === key ? null : key)}>+</button></td>
                <td className="code"><span className="sign">{r.kind === "add" ? "+" : r.kind === "del" ? "-" : " "}</span>{r.text}</td>
              </tr>
              {(has || openAt === key) && (
                <tr className="comment-row"><td colSpan={3} /><td>
                  <Comments reviewId={reviewId} comments={comments} kind="line" anchor={anchor} onChange={onComments} />
                </td></tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
```

`frontend/src/components/Files.tsx`:

```tsx
import { useState } from "react";
import type { Comment, FileChange } from "../api";
import DiffView from "./DiffView";

interface Props { reviewId: number; files: FileChange[]; comments: Comment[]; onComments: () => void }

export default function Files({ reviewId, files, comments, onComments }: Props) {
  const [view, setView] = useState<string>("cumulative");
  const cls = [...new Set(files.flatMap((f) => f.per_cl.map((p) => p.cl)))].sort((a, b) => a - b);
  return (
    <div className="files">
      <div className="toolbar">
        <label>Diff <select value={view} onChange={(e) => setView(e.target.value)}>
          <option value="cumulative">cumulative (all CLs)</option>
          {cls.map((cl) => <option key={cl} value={String(cl)}>CL {cl} only</option>)}
        </select></label>
      </div>
      {files.map((f) => {
        const cl = view === "cumulative" ? null : Number(view);
        const step = cl === null ? null : f.per_cl.find((p) => p.cl === cl);
        if (cl !== null && !step) return null;
        return (
          <details key={f.depot} open className="card file">
            <summary><span className="mono">{f.depot}</span> <span className="badge">{f.action}</span>
              {f.base_rev && <span className="muted small"> base {f.base_rev}</span>}</summary>
            <DiffView reviewId={reviewId} depot={f.depot} cl={cl} before={step ? step.before : f.before}
                      after={step ? step.after : f.after} comments={comments} onComments={onComments} />
          </details>
        );
      })}
    </div>
  );
}
```

`frontend/src/components/ClsPanel.tsx`:

```tsx
import { useState } from "react";
import { api, type ClRow } from "../api";
import { useMe } from "../App";

export default function ClsPanel({ reviewId, cls, onChange }: { reviewId: number; cls: ClRow[]; onChange: () => void }) {
  const me = useMe();
  const [msg, setMsg] = useState<string | null>(null);
  const run = (p: Promise<unknown>, ok: string) => p.then(() => { setMsg(ok); onChange(); }).catch((e) => setMsg(String(e.message ?? e)));
  return (
    <div className="cls">
      {msg && <div className="banner">{msg}</div>}
      <table className="table">
        <thead><tr><th>CL</th><th>Status</th><th>Author</th><th>Description</th><th>Swarm</th>{me?.is_owner && <th />}</tr></thead>
        <tbody>
          {cls.map((c) => (
            <tr key={c.cl}>
              <td className="mono">{c.cl}</td>
              <td>{c.status}</td>
              <td>{c.user}</td>
              <td className="small">{c.description}</td>
              <td>{c.swarm ? (
                <a href={c.swarm.url} target="_blank" rel="noreferrer">#{c.swarm.id} {c.swarm.state_label ?? c.swarm.state}</a>
              ) : <span className="muted">none</span>}
                {c.swarm && Object.keys(c.swarm.votes).length > 0 && (
                  <div className="small muted">{Object.entries(c.swarm.votes).map(([u, v]) => `${u} ${v > 0 ? "+" : ""}${v}`).join(", ")}</div>
                )}
              </td>
              {me?.is_owner && (
                <td className="actions">
                  <button className="link small" onClick={() => run(api.swarmRefresh(reviewId, c.cl), "Swarm state refreshed")}>refresh</button>
                  {!c.swarm && c.status === "pending" && (
                    <button className="link small" onClick={() => run(api.swarmCreate(reviewId, c.cl), "Swarm review created")}>create review</button>
                  )}
                  {c.swarm && (
                    <button className="link small" onClick={() => run(
                      api.swarmPost(reviewId, c.cl).catch((e) => {
                        if (e.status === 409 && confirm("A summary was already posted. Post again?")) return api.swarmPost(reviewId, c.cl, true);
                        throw e;
                      }), "Summary link posted to Swarm")}>post summary link</button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

`frontend/src/pages/Review.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, type Comment, type FileChange, type Finding, type Impact, type ReviewDetail, type StoryboardResponse } from "../api";
import { useMe } from "../App";
import { RiskBadge, StatusBadge } from "../components/Badges";
import BlastRadius from "../components/BlastRadius";
import CallFlows from "../components/CallFlows";
import ClsPanel from "../components/ClsPanel";
import Files from "../components/Files";
import Findings from "../components/Findings";
import Stages from "../components/Stages";
import Storyboard from "../components/Storyboard";

const TERMINAL = new Set(["done", "degraded", "failed"]);

export default function Review() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [sb, setSb] = useState<StoryboardResponse | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch((e) => setError(String(e.message ?? e))), [id]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadResults = useCallback(() => Promise.all([
    api.storyboard(id).then(setSb), api.impact(id).then(setImpact), loadFindings(), api.files(id).then(setFiles), loadComments(),
  ]), [id, loadFindings, loadComments]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  const status = detail?.review.status;
  useEffect(() => {
    if (!status) return;
    if (TERMINAL.has(status)) { loadResults(); return; }
    const es = new EventSource(`/api/reviews/${id}/events`);
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setDetail((d) => (d ? { ...d, review: data.review, stages: data.stages } : d));
      if (TERMINAL.has(data.review.status)) { es.close(); loadDetail(); }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [id, status, loadResults, loadDetail]);

  const layerName = useCallback((level: number | null) => {
    const layer = sb?.storyboard?.chapters.find((c) => c.level === level);
    return layer?.name ?? (level === null ? "unlayered" : `L${level}`);
  }, [sb]);

  const onCite = useCallback((cite: string) => {
    setFocus(cite);
    navigate(cite.startsWith("F") ? `/r/${id}/findings` : `/r/${id}/flows`);
  }, [id, navigate]);

  if (error) return <main className="page error">{error}</main>;
  if (!detail) return <main className="page muted">Loading…</main>;
  const r = detail.review;
  const ready = TERMINAL.has(r.status);
  return (
    <main className="page wide">
      <div className="review-head">
        <h1>{r.title}</h1>
        <StatusBadge status={r.status} />
        <RiskBadge risk={r.risk} />
        <span className="mono muted">CLs {r.cls.join(", ")}</span>
        {me?.is_owner && ready && <button className="link" onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button>}
      </div>
      <Stages stages={detail.stages} />
      {detail.stages.filter((s) => s.status === "failed" || s.status === "degraded").map((s) => (
        <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>
      ))}
      <nav className="tabs">
        {[["storyboard", "Storyboard"], ["flows", "Call flows"], ["blast", "Blast radius"],
          ["findings", `Findings (${findings.length})`], ["files", `Files (${files.length})`], ["cls", "CLs & Swarm"]].map(([p, label]) => (
          <NavLink key={p} to={`/r/${id}/${p}`} className={({ isActive }) => (isActive ? "on" : "")}>{label}</NavLink>
        ))}
      </nav>
      {!ready ? <p className="muted">Analysis in progress…</p> : (
        <Routes>
          <Route index element={<Navigate to="storyboard" replace />} />
          <Route path="storyboard" element={sb?.storyboard ? (
            <Storyboard reviewId={id} sb={sb.storyboard} drift={sb.drift} impact={impact} findings={findings}
                        comments={comments} onComments={loadComments} onCite={onCite}
                        onRenamed={() => api.storyboard(id).then(setSb)} />
          ) : <p className="muted">No storyboard (see stage messages above).</p>} />
          <Route path="flows" element={impact ? (
            <CallFlows reviewId={id} impact={impact} findings={findings} comments={comments} onComments={loadComments}
                       focus={focus && focus.startsWith("N") ? focus : null} onCite={onCite} layerName={layerName} />
          ) : <p className="muted">No impact model.</p>} />
          <Route path="blast" element={impact ? <BlastRadius impact={impact} onCite={onCite} layerName={layerName} /> : <p className="muted">No impact model.</p>} />
          <Route path="findings" element={
            <Findings reviewId={id} findings={findings} focus={focus && focus.startsWith("F") ? focus : null} comments={comments}
                      onComments={loadComments} onFindings={loadFindings} onCite={onCite} />} />
          <Route path="files" element={<Files reviewId={id} files={files} comments={comments} onComments={loadComments} />} />
          <Route path="cls" element={<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />} />
        </Routes>
      )}
    </main>
  );
}
```

`frontend/src/App.tsx` (replace the whole file):

```tsx
import { createContext, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, type Me } from "./api";
import Health from "./pages/Health";
import Login from "./pages/Login";
import NewReview from "./pages/NewReview";
import Review from "./pages/Review";
import Reviews from "./pages/Reviews";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, [location.pathname]);

  if (me === undefined) return <div className="page muted">Loading…</div>;
  if (me === null && location.pathname !== "/login")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;

  return (
    <MeContext.Provider value={me}>
      <header className="topbar">
        <Link to="/" className="brand">CodeTortoise</Link>
        {me && (
          <nav>
            <Link to="/">Reviews</Link>
            {me.is_owner && <Link to="/new">New review</Link>}
            {me.is_owner && <Link to="/health">Health</Link>}
            <span className="muted">{me.user}</span>
            <button className="link" onClick={() => api.logout().then(() => { setMe(null); navigate("/login"); })}>
              Log out
            </button>
          </nav>
        )}
      </header>
      <Routes>
        <Route path="/login" element={<Login onLogin={() => api.me().then(setMe)} />} />
        <Route path="/" element={<Reviews />} />
        <Route path="/new" element={<NewReview />} />
        <Route path="/health" element={<Health />} />
        <Route path="/r/:id/*" element={<Review />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MeContext.Provider>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npm test && npm run build`
Expected: 7 vitest tests pass; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CiteText.tsx frontend/src/components/Comments.tsx frontend/src/components/Stages.tsx frontend/src/components/Storyboard.tsx frontend/src/components/Findings.tsx frontend/src/components/CallFlows.tsx frontend/src/components/BlastRadius.tsx frontend/src/components/DiffView.tsx frontend/src/components/Files.tsx frontend/src/components/ClsPanel.tsx frontend/src/pages/Review.tsx frontend/src/App.tsx
git commit -m "feat(frontend): review page with storyboard, call flows, blast radius, findings, files and Swarm panel"
```

---

### Task 23: End-to-end smoke test and README

A Playwright test starts the real server on the bundled fixture (`e2e/serve.sh` → `fixture-demo` + `serve`
on port 8799, dev auth, no LLM) and drives the full flow: sign in, create a review of CLs 101 102, see the
storyboard's layer chapter, render the call-flow graph, find the alias finding, and leave a line comment.
The README documents the quick start and the Perforce configuration.

**Files:**
- Create: `README.md`
- Test: `frontend/playwright.config.ts`
- Test: `frontend/e2e/serve.sh`
- Test: `frontend/e2e/smoke.spec.ts`

**Interfaces:**
- Consumes: the whole application.
- `e2e/serve.sh` honours `TORTOISE_CMD` (default `uv run --project ../backend codetortoise`).

- [ ] **Step 1: Write the failing tests**

`frontend/playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:8799" },
  webServer: { command: "./e2e/serve.sh", url: "http://127.0.0.1:8799/api/me", timeout: 120_000, reuseExistingServer: false },
});
```

`frontend/e2e/serve.sh`:

```bash
#!/usr/bin/env bash
# Starts CodeTortoise on the bundled fixture for end-to-end tests.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8799 >/dev/null
exec $CMD serve --config "$DIR/tortoise.yaml"
```

`frontend/e2e/smoke.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("owner reviews fixture CLs end to end", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("P4 user").fill("demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();

  await page.getByRole("link", { name: "New review" }).click();
  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "L2: driver" })).toBeVisible();

  await page.getByRole("link", { name: "Call flows" }).click();
  await expect(page.getByTestId("flow-graph").locator("canvas").first()).toBeAttached();

  await page.getByRole("link", { name: /Findings/ }).click();
  await expect(page.getByText("uart_send now writes Uart::errors through a local alias")).toBeVisible();

  await page.getByRole("link", { name: /Files/ }).click();
  const row = page.locator("tr.add", { hasText: "return -2;" });
  await row.hover();
  await row.getByTitle("Comment on this line").click();
  await page.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
  await page.getByRole("button", { name: "Comment" }).click();
  await expect(page.getByText("Does logger_flush handle -2?")).toBeVisible();
});
```

- [ ] **Step 2: Implement**

`README.md`:

````markdown
# CodeTortoise

Deep, layered code review for C/C++ Perforce changelists. CodeTortoise turns one or more CLs into a
**storyboard**: changes grouped by inferred architectural layer, before/after call flows, blast radius
over call *and* field-data coupling (including writes through local pointer/reference aliases), and
findings with cited static-analysis evidence. An OpenAI-compatible LLM (your endpoint, your key) writes
the narrative; every claim it makes must cite analysis facts.

The web app is the system of record for review discussion. P4 Swarm is a side channel: CodeTortoise reads
review state, can create a review for a shelved CL, and posts a summary link.

## Quick start (bundled fixture, no Perforce needed)

```bash
cd backend && uv sync && cd ..
cd frontend && npm install && npm run build && cd ..
uv run --project backend codetortoise fixture-demo --dir /tmp/tortoise-demo
uv run --project backend codetortoise serve --config /tmp/tortoise-demo/tortoise.yaml
# open http://127.0.0.1:8765, log in as "demo", start a review of CLs 101 102
```

Headless: `uv run --project backend codetortoise review --config /tmp/tortoise-demo/tortoise.yaml 101 102`

## Real setup (Perforce)

`tortoise.yaml`:

```yaml
owner: anoop                        # your P4 user; the only one who can create reviews
server: {host: 0.0.0.0, port: 8765, public_url: "http://myhost:8765", data_dir: .tortoise}
workspace:                          # an existing, synced client; never modified
  vcs: p4
  p4port: ssl:p4:1666
  client: anoop-main-ws
  root: /work/main                  # must equal the client's Root
  compile_commands: /work/main/build/compile_commands.json
toolchain:
  clang: /opt/vendor/bin/clang      # vendor driver, queried for implicit includes/macros
  libclang: /opt/vendor/lib/libclang.so   # optional; bundled libclang is used otherwise
  strip_flags: []                   # vendor flags libclang must ignore (unknown ones are auto-stripped)
swarm: {url: "https://swarm.example.com"}
llm: {base_url: "https://llm.example.com/v1", model: "your-model", api_key_env: TORTOISE_LLM_KEY}
auth: {mode: p4}
```

```bash
export TORTOISE_LLM_KEY=...                      # never stored or logged
uv run --project backend codetortoise index --config tortoise.yaml   # first run: repo-wide symbol index
uv run --project backend codetortoise serve --config tortoise.yaml
```

Colleagues open the shared link and sign in with their P4 credentials (`p4 login -p`; passwords and
tickets are not stored). The server is meant for a trusted LAN/VPN; put it behind a TLS reverse proxy if
it leaves one. Code snippets of changed functions and their callers are sent to the configured LLM.

## Development

```bash
cd backend && uv run pytest && uv run ruff check codetortoise tests
cd frontend && npm test && npm run build && npm run e2e
```

Design: `docs/superpowers/specs/2026-09-29-codetortoise-design.md`.
````

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run build && npx playwright install chromium && npm run e2e`
Expected: `1 passed`.

- [ ] **Step 4: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/serve.sh frontend/e2e/smoke.spec.ts README.md
git commit -m "test(e2e): Playwright smoke over the fixture; docs: README"
```

---

## Spec Coverage (M1)

| Spec section | Where |
|---|---|
| §3 config and startup validation | Tasks 1, 17 (`run_health`), 18 (409 when not ready), 21 (Health page) |
| §4 units | Tasks 2–19; one module per unit |
| §5.1 ingest, stacking, drift | Tasks 3, 4 |
| §5.2 DiffMap | Task 5 |
| §5.3 TU selection | Task 9 |
| §5.4 toolchain and clang facts | Tasks 6, 10 |
| §5.5 alias-aware field mutation | Task 8 (intraprocedural and direct may-write-via-call; interprocedural summaries are M2) |
| §5.6 impact model | Task 11 |
| §5.7 detectors (`contract`, `field_mutation`, `header_fanout`) | Task 12 (the other detectors are M2) |
| §5.8 layers | Tasks 9, 14 (`name_layers`), 17 (cache), 18 (rename) |
| §5.9 LLM and grounding | Tasks 13, 14 |
| §5.10 pipeline | Task 17 |
| §6 storage | Task 15 (see §14 for the blob layout) |
| §7 web UI | Tasks 18, 20–22 |
| §8 Swarm | Tasks 16, 18, 22 |
| §9 error handling | Tasks 10, 13, 14, 17 |
| §10 security notes | Tasks 4, 15, 18, README (Task 23) |
| §11 testing | Every task; e2e in Task 23 (live `p4d` test deferred, see §14) |

## After M1

Run `codetortoise review --config tortoise.yaml <CL>…` against a real CL set on the vendor toolchain first. Check the facts stage message (degraded TUs and stripped flags) and the Health page before tuning `tu_budget` or `module_min_files`. M2 then adds interprocedural write summaries, the `shared_state`, `concurrency` and `abi_virtual` detectors, callback-registration entry points, a persistent parse cache, incremental index refresh via `p4 have`, and automatic re-runs when a shelf changes.
