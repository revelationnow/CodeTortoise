"""`codetortoise init`: write a starter tortoise.yaml from what the workspace already knows.

It reads the Perforce settings the way p4 does (P4CONFIG file, then environment), asks Perforce for the client's Root
(read-only `p4 client -o`), looks for compile_commands.json under the workspace and takes the compiler from its first
entry. Anything it cannot find is left commented, with how to find it.
"""
from __future__ import annotations

import json
import os
import shlex
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from codetortoise.toolchain.compile_db import _compiler_words
from codetortoise.vcs.p4settings import p4_settings

SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".svn", ".tortoise"}
MAX_DEPTH = 2          # compile_commands.json in the root, build/, or build/<config>/


@dataclass
class Scan:
    root: Path
    values: dict[str, str | None]                  # owner, p4port, client
    sources: dict[str, str | None]                 # where each value came from
    client_root: str | None = None
    root_matches_client: bool | None = None
    compile_dbs: list[Path] = field(default_factory=list)
    compiler: str | None = None
    notes: list[str] = field(default_factory=list)
    root_guessed: bool = False                     # from where the P4CONFIG file is, not from Perforce


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _walk(top: Path, depth0: int) -> list[tuple[int, Path]]:
    found = []
    for dirpath, dirnames, filenames in os.walk(top, followlinks=True):     # depth-limited, so links are safe
        depth = depth0 + len(Path(dirpath).relative_to(top).parts)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS) if depth < MAX_DEPTH else []
        if "compile_commands.json" in filenames:
            found.append((depth, Path(dirpath) / "compile_commands.json"))
    return found


def _compile_dbs(root: Path) -> list[Path]:
    """compile_commands.json under the workspace, then in build/out folders beside it (out-of-tree builds)."""
    found = _walk(root, 0)
    for side in sorted(root.parent.iterdir()) if root.parent != root else []:
        if side != root and side.is_dir() and side.name.lower().startswith(("build", "out", "_build", "cmake-build")):
            found += [(d + 1, p) for d, p in _walk(side, 1)]
    seen: set[str] = set()                      # the same database reached through a link counts once
    return [p for _, p in sorted(found) if not (os.path.realpath(p) in seen or seen.add(os.path.realpath(p)))]


def _compiler(db: Path) -> str | None:
    try:
        entry = json.loads(db.read_text())[0]
        args = _compiler_words(entry.get("arguments") or shlex.split(entry.get("command", "")))   # past any wrapper
        return args[0] if args else None
    except (OSError, ValueError, IndexError, KeyError, AttributeError):
        return None


def scan(start: Path, env: Mapping[str, str] | None = None,
         client_root: Callable[[str, str], str | None] | None = None) -> Scan:
    """What `init` knows about the workspace containing `start`. `client_root(port, client)` asks Perforce for the
    client's Root (None to skip)."""
    start = Path(start).resolve()
    p4 = p4_settings(start, env)
    keys = {"owner": "P4USER", "p4port": "P4PORT", "client": "P4CLIENT"}
    values = {k: p4.get(v) for k, v in keys.items()}
    sources = {k: p4.source(v) for k, v in keys.items()}
    s = Scan(root=start, values=values, sources=sources)
    if client_root and values["p4port"] and values["client"]:
        try:
            s.client_root = client_root(values["p4port"], values["client"])
        except Exception as e:  # init still writes what it knows
            hint = " — run `p4 login -a`, then run init again" if "login" in str(e).lower() else ""
            s.notes.append(f"could not read the client's Root (p4 client -o {values['client']}): {e}{hint}")
    if s.client_root:
        croot = Path(s.client_root).resolve()
        if _inside(start, croot):
            s.root = croot
        s.root_matches_client = s.root == croot
    elif p4.file is not None and _inside(start, p4.file.parent.resolve()):
        s.root, s.root_guessed = p4.file.parent.resolve(), True  # a P4CONFIG file usually sits at the workspace root
    s.compile_dbs = _compile_dbs(s.root)
    s.compiler = _compiler(s.compile_dbs[0]) if s.compile_dbs else None
    return s


HOW = {
    "owner": "your Perforce user name, the one who starts reviews (p4 info: User name)",
    "p4port": "the Perforce server address (p4 info: Server address), e.g. ssl:perforce.example.com:1666",
    "client": "the workspace (client) name (p4 info: Client name)",
}


def _value(key: str, s: Scan, indent: str) -> str:
    v, src = s.values[key], s.sources[key]
    if v and src and src.startswith("P4CONFIG"):        # leave it to the file, so the two stay in sync
        return f"{indent}# {key}: {v}   # read from the {src}; set it here only to override\n"
    if v:
        return f"{indent}{key}: {v}   # from {src}\n"
    return f"{indent}# {key}:   # check: {HOW[key]}\n"


def render(s: Scan) -> str:
    """A commented tortoise.yaml for `s`."""
    out = [f"# tortoise.yaml written by `codetortoise init` on {date.today().isoformat()}.\n",
           "# Read every line marked \"check:\". Relative paths are resolved against this file's directory.\n\n",
           _value("owner", s, ""),
           "server:\n",
           "  host: 127.0.0.1                 # this machine only; 0.0.0.0 to share on the network (then set tls_cert/tls_key)\n",
           "  port: 8765\n",
           "  public_url: http://127.0.0.1:8765   # the address colleagues open; shared links point here\n",
           "  data_dir: .tortoise             # database, symbol index and caches\n",
           "workspace:\n",
           "  vcs: p4\n",
           _value("p4port", s, "  "),
           _value("client", s, "  ")]
    if s.root_matches_client is False:
        out.append(f"  # check: the client's Root is {s.client_root}; root must equal it (or one of its AltRoots)\n")
    if s.root_guessed:
        out.append("  # check: guessed from where the P4CONFIG file is; it must equal the client's Root (p4 client -o)\n")
    out.append(f"  root: {s.root}\n")
    top = Path(os.path.commonpath([str(d.parent) for d in s.compile_dbs])) if len(s.compile_dbs) > 1 else None
    if top is not None and (top == s.root or s.root in top.parents or top.parent == s.root.parent):
        out.append("  compile_commands: auto           # every compile_commands.json under build_root; the deepest wins\n")
        out.append(f"  build_root: {top}\n")
        out += [f"  #   found: {d}\n" for d in s.compile_dbs]
    elif top is not None:                       # spread above the workspace: list them, never search that far up
        out.append("  compile_commands:                # first listed wins for files in more than one\n")
        out += [f"    - {d}\n" for d in s.compile_dbs]
    elif s.compile_dbs:
        out.append(f"  compile_commands: {s.compile_dbs[0]}\n")
    else:
        out.append(f"  # compile_commands:   # check: compile_commands.json not found under {s.root}; "
                   "generate it (see the README) and put its path here\n")
    out.append("toolchain:\n")
    if s.compiler:
        out.append(f"  # clang: {s.compiler}   # only if the build's compilers aren't on this machine: "
                   "it replaces every file's own compiler\n")
    else:
        out.append("  # clang: /path/to/your/compiler   # check: the compiler your build uses\n")
    out += ["  strip_flags: []\n",
            "# swarm:\n",
            "#   url: https://swarm.example.com   # optional: read and post Swarm reviews\n",
            "# llm:                               # optional: AI-written narratives (code is sent to this endpoint)\n",
            "#   base_url: https://llm.example.com/v1\n",
            "#   model: your-model\n",
            "#   api_key_env: TORTOISE_LLM_KEY\n",
            "auth:\n",
            "  mode: p4                        # sign in with Perforce credentials\n"]
    return "".join(out)


def summary(s: Scan, out: Path) -> str:
    lines = [f"wrote {out}", f"  workspace root: {s.root}"]
    for key in ("owner", "p4port", "client"):
        lines.append(f"  {key}: {s.values[key]} ({s.sources[key]})" if s.values[key] else f"  {key}: not found — set it")
    if s.root_matches_client is False:
        lines.append(f"  the client's Root is {s.client_root}, not {s.root}: fix one of them")
    lines.append(f"  compile_commands: {s.compile_dbs[0] if s.compile_dbs else 'not found — generate it (README)'}")
    lines.append(f"  compiler: {s.compiler or 'not found'}")
    lines += [f"  note: {n}" for n in s.notes]
    lines += ["next:",
              f"  codetortoise index --config {out}",
              f"  codetortoise serve --config {out}",
              "  then sign in as the owner and open the Health page"]
    return "\n".join(lines)
