#!/usr/bin/env python3
"""Builds a Perforce history from a git project, for testing CodeTortoise on large changes by hand.

Imports the base snapshot, then for each chosen commit one catch-up changelist (everything between the previous
point and the commit's first parent) and the commit itself as one changelist. Commits given to --shelve become pending
changelists, shelved on top of head at that point. Writes a TSV of the changelists
(C files and directories count C/C++ files outside tests). Run by hand, never as a service:
if no server answers at --port and --root is given, it starts p4d in the background and says how to stop it.

  lab/p4-import.py --repo https://github.com/libgit2/libgit2.git --clone $LAB/upstream --base <sha> --end main \\
      --depot //depot/libgit2-big --workspace $LAB/big-ws --client big-ws --exclude tests/resources --out $LAB/big-cls.tsv
  lab/p4-import.py --repo $LAB/upstream --base <sha> --end main --list      # the commits it would pick
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

C_EXT = {".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".inl"}
TEST_DIRS = {"test", "tests", "testing", "unittest", "unittests"}
BATCH = 2000


def die(msg: str) -> None:
    print(f"p4-import: {msg}", file=sys.stderr)
    sys.exit(1)


# --- git -------------------------------------------------------------------------------------------------------------

class Git:
    def __init__(self, repo: str, clone: str | None):
        if re.match(r"^[a-z+]+://|^git@", repo):
            dest = Path(clone or Path.cwd() / posixpath.basename(repo.rstrip("/")).removesuffix(".git"))
            if not dest.exists():
                print(f"cloning {repo} into {dest}")
                subprocess.run(["git", "clone", "-q", "--bare", repo, str(dest)], check=True)
            repo = str(dest)
        self.dir = repo
        self.env = os.environ | {"GIT_LITERAL_PATHSPECS": "1"}

    def __call__(self, *args: str, input: bytes | None = None, env: dict | None = None) -> bytes:
        r = subprocess.run(["git", "-C", self.dir, *args], input=input, capture_output=True, env=env or self.env)
        if r.returncode:
            die(f"git {' '.join(args[:3])}: {r.stderr.decode(errors='replace').strip()}")
        return r.stdout

    def sha(self, rev: str) -> str:
        return self("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()

    def subject(self, sha: str) -> str:
        return self("log", "-1", "--format=%s", sha).decode().strip()

    def first_parent(self, sha: str) -> str:
        return self.sha(f"{sha}^1")

    def chain(self, base: str, end: str) -> list[str]:
        return self("rev-list", "--first-parent", "--reverse", f"{base}..{end}").decode().split()

    def diff(self, a: str, b: str) -> list[Change]:
        """Changes from a to b, renames as a delete and an add."""
        out = self("diff", "--raw", "--no-renames", "-z", "--no-abbrev", a, b).decode(errors="surrogateescape")
        parts = out.split("\0")
        changes = []
        for meta, path in zip(parts[0::2], parts[1::2], strict=False):
            if not meta:
                continue
            old_mode, new_mode, _, _, status = meta.lstrip(":").split()
            changes.append(Change(path, status[0], old_mode, new_mode))
        return changes

    def files(self, rev: str) -> list[Change]:
        out = self("ls-tree", "-r", "-z", "--full-tree", rev).decode(errors="surrogateescape")
        changes = []
        for entry in filter(None, out.split("\0")):
            meta, path = entry.split("\t", 1)
            mode, kind, _ = meta.split()
            if kind == "blob":
                changes.append(Change(path, "A", "000000", mode))
        return changes

    def checkout(self, rev: str, paths: list[str], dest: Path) -> None:
        """Writes rev's version of paths into dest, with their modes and symlinks."""
        if not paths:
            return
        with tempfile.TemporaryDirectory() as tmp:
            env = self.env | {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
            self("read-tree", rev, env=env)
            self("--work-tree", str(dest), "checkout-index", "-f", "-z", "--stdin",
                 input="\0".join(paths).encode(errors="surrogateescape"), env=env)


@dataclass
class Change:
    path: str
    status: str        # A, M, D or T (type change)
    old_mode: str
    new_mode: str


def is_c(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in C_EXT


def is_test(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return bool(TEST_DIRS & set(parts[:-1])) or name.startswith("test_") or bool(re.search(r"_tests?\.\w+$", name))


def c_stats(changes: list[Change]) -> tuple[int, int]:
    """C/C++ files outside tests, and their directories."""
    files = [c.path for c in changes if is_c(c.path) and not is_test(c.path)]
    return len(files), len({posixpath.dirname(f) for f in files})


def excluded(path: str, patterns: list[str]) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") or fnmatch.fnmatch(path, p) for p in patterns)


# --- p4 --------------------------------------------------------------------------------------------------------------

def escape(path: str) -> str:
    return path.replace("%", "%25").replace("@", "%40").replace("#", "%23").replace("*", "%2A")


class P4:
    def __init__(self, port: str, client: str, cwd: Path):
        self.port, self.client, self.cwd = port, client, cwd

    def __call__(self, *args: str, input: str | None = None, check: bool = True) -> str:
        r = subprocess.run(["p4", "-p", self.port, "-c", self.client, *args], input=input, capture_output=True, text=True,
                           cwd=self.cwd)
        if check and (r.returncode or r.stderr.strip() and "no such file" not in r.stderr and "file(s) not" not in r.stderr):
            die(f"p4 {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()}")
        return r.stdout

    def batch(self, args: list[str], paths: list[str]) -> None:
        for i in range(0, len(paths), BATCH):
            self("-x", "-", *args, input="\n".join(paths[i:i + BATCH]) + "\n")


def ensure_server(port: str, root: str | None, password: str) -> int | None:
    """Returns the pid of a p4d this run started, or None when one was already answering. A new server needs a
    password: the first user sets one (and becomes super), as lab/setup.sh does, and logs in."""
    if subprocess.run(["p4", "-p", port, "info"], capture_output=True).returncode == 0:
        return None
    if not root:
        die(f"no Perforce server answers at {port}; pass --root to start one")
    r = Path(root)
    r.mkdir(parents=True, exist_ok=True)
    log = open(r / "p4d.out", "ab")                                       # noqa: SIM115 (kept open for the daemon)
    proc = subprocess.Popen(["p4d", "-r", str(r), "-p", port, "-L", str(r / "log"), "-J", str(r / "journal")],
                            stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    (r / "p4d.pid").write_text(str(proc.pid))
    for _ in range(100):
        if subprocess.run(["p4", "-p", port, "info"], capture_output=True).returncode == 0:
            for cmd, given in ((["passwd"], f"{password}\n{password}\n"), (["login"], f"{password}\n")):
                out = subprocess.run(["p4", "-p", port, *cmd], input=given, capture_output=True, text=True)
                if out.returncode:
                    die(f"p4 {cmd[0]} on the new server: {(out.stderr or out.stdout).strip()}")
            print(f"started p4d (pid {proc.pid}) at {port} under {r}; stop it with: kill {proc.pid}")
            return proc.pid
        if proc.poll() is not None:
            die(f"p4d exited ({proc.returncode}); see {r / 'p4d.out'}")
        time.sleep(0.1)
    die(f"p4d did not answer at {port}")
    return None


def setup(p4: P4, depot: str, ws: Path) -> None:
    depot = depot.rstrip("/").removesuffix("/...")
    if p4("files", "-m1", f"{depot}/...", check=False).strip():
        die(f"{depot}/... already has files; choose a new --depot")
    if ws.exists() and any(ws.iterdir()):
        die(f"workspace {ws} is not empty")
    ws.mkdir(parents=True, exist_ok=True)
    name = depot.split("/")[2]
    if f"Depot {name} " not in p4("depots"):
        p4("depot", "-i", input=p4("depot", "-o", name))
    spec = p4("--field", f"Root={ws}", "--field", f"View={depot}/... //{p4.client}/...",
              "--field", "Options=allwrite clobber nocompress unlocked nomodtime rmdir", "client", "-o", p4.client)
    p4("client", "-i", input=spec)


def open_changes(p4: P4, git: Git, rev: str, changes: list[Change], ws: Path) -> int:
    """Opens changes (git's version at rev) in the default changelist. Returns how many files were opened."""
    local = lambda c: str(ws / c.path)                                    # noqa: E731
    deletes = [c for c in changes if c.status == "D"]
    edits = [c for c in changes if c.status in "MT"]
    adds = [c for c in changes if c.status == "A"]
    p4.batch(["delete"], [escape(local(c)) for c in deletes])
    p4.batch(["edit"], [escape(local(c)) for c in edits])
    for c in edits:
        if c.new_mode == "120000" or c.old_mode == "120000":           # git writes a symlink over the file and back
            Path(local(c)).unlink(missing_ok=True)
    git.checkout(rev, [c.path for c in edits + adds], ws)
    p4.batch(["add", "-f"], [local(c) for c in adds if c.new_mode != "100755"])
    p4.batch(["add", "-f", "-t", "+x"], [local(c) for c in adds if c.new_mode == "100755"])
    for c in edits:                                                       # executable bit or symlink changed
        if c.old_mode == c.new_mode:
            continue
        if c.new_mode == "120000":
            p4("reopen", "-t", "symlink", escape(local(c)))
        elif c.new_mode == "100755":
            p4("reopen", "-t", "text+x" if c.old_mode == "120000" else "+x", escape(local(c)))
        else:
            head = p4("-ztag", "-F", "%headType%", "fstat", escape(local(c))).strip()
            p4("reopen", "-t", "text" if c.old_mode == "120000" else plain(head), escape(local(c)))
    return len(changes)


def plain(filetype: str) -> str:
    """The filetype without the executable modifier: text+x and xtext become text."""
    base, _, mods = {"xtext": "text+x", "xbinary": "binary+x", "kxtext": "text+kx", "cxtext": "text+Cx",
                     "xunicode": "unicode+x", "xutf16": "utf16+x"}.get(filetype, filetype).partition("+")
    mods = mods.replace("x", "")
    return base + (f"+{mods}" if mods else "")


def submit(p4: P4, desc: str) -> str:
    out = p4("-ztag", "submit", "-d", desc)
    m = re.search(r"submittedChange (\d+)", out)
    if not m:
        die(f"submit gave no changelist: {out.strip()}")
    return m.group(1)


def shelve(p4: P4, desc: str) -> str:
    spec = p4("--field", f"Description={desc}", "change", "-o")
    m = re.search(r"Change (\d+) created", p4("change", "-i", input=spec))
    if not m:
        die("could not create a pending changelist")
    cl = m.group(1)
    p4("shelve", "-c", cl)
    p4("revert", "-w", "-c", cl, f"//{p4.client}/...")
    return cl


# --- main ------------------------------------------------------------------------------------------------------------

def pick(git: Git, base: str, end: str, min_files: int, excludes: list[str]) -> list[tuple[str, int, int]]:
    out = []
    for sha in git.chain(base, end):
        changes = [c for c in git.diff(git.first_parent(sha), sha) if not excluded(c.path, excludes)]
        n, dirs = c_stats(changes)
        if n >= min_files:
            out.append((sha, n, dirs))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="git URL or local clone")
    ap.add_argument("--clone", help="where to clone a URL (default: ./<name>)")
    ap.add_argument("--base", required=True, help="commit to import as the starting snapshot")
    ap.add_argument("--end", default="HEAD", help="last commit of the range to pick from (default HEAD)")
    ap.add_argument("--commits", nargs="*", default=None, help="exact commits to import (default: picked by --min-files)")
    ap.add_argument("--min-files", type=int, default=30,
                    help="pick first-parent commits touching this many C/C++ files outside tests")
    ap.add_argument("--shelve", nargs="*", default=[], help="commits to shelve as pending changelists instead of submitting")
    ap.add_argument("--exclude", action="append", default=[], help="path prefix or glob to leave out (repeatable)")
    ap.add_argument("--list", action="store_true", help="print the picked commits (sha, C files, directories, subject) and stop")
    ap.add_argument("--depot", default="//depot/libgit2-big", help="depot path to import into (must be empty)")
    ap.add_argument("--workspace", help="client root (must be empty)")
    ap.add_argument("--client", default="big-ws")
    ap.add_argument("--port", default=os.environ.get("P4PORT", "127.0.0.1:1666"))
    ap.add_argument("--root", help="p4d root, used to start a server if none answers at --port")
    ap.add_argument("--password", default=os.environ.get("OWNER_PASSWD", "TortoiseLab-2026"),
                    help="password set for you on a server this run starts (default as lab/setup.sh)")
    ap.add_argument("--out", default="cls.tsv", help="where to write the changelist table")
    a = ap.parse_args()

    git = Git(a.repo, a.clone)
    base, end = git.sha(a.base), git.sha(a.end)
    chain = git.chain(base, end)
    if a.list:
        for sha, n, dirs in pick(git, base, end, a.min_files, a.exclude):
            print(f"{sha[:9]}\t{n}\t{dirs}\t{git.subject(sha)}")
        return
    if not a.workspace:
        die("--workspace is required to import")
    if a.commits is not None:
        chosen = [git.sha(c) for c in a.commits]
    else:
        chosen = [s for s, _, _ in pick(git, base, end, a.min_files, a.exclude)]
    shelved = {git.sha(c) for c in a.shelve}
    order = {s: i for i, s in enumerate(chain)}
    for s in set(chosen) | shelved:
        if s not in order:
            die(f"{s[:9]} is not a first-parent commit between --base and --end")
    todo = sorted(set(chosen) | shelved, key=order.__getitem__)
    if not todo:
        die("no commits to import; lower --min-files or pass --commits")

    ensure_server(a.port, a.root, a.password)
    ws = Path(a.workspace).resolve()
    p4 = P4(a.port, a.client, Path.cwd())
    setup(p4, a.depot, ws)
    p4.cwd = ws
    keep = lambda cs: [c for c in cs if not excluded(c.path, a.exclude)]  # noqa: E731
    rows = []

    def record(cl: str, kind: str, sha: str, subject: str, changes: list[Change]) -> None:
        n, dirs = c_stats(changes)
        rows.append((cl, kind, sha[:9], subject, n, dirs))
        print(f"CL {cl}\t{kind}\t{sha[:9]}\t{n} C files in {dirs} directories\t{subject}")

    changes = keep(git.files(base))
    open_changes(p4, git, base, changes, ws)
    record(submit(p4, f"import at upstream {base[:9]}"), "base", base, "", changes)
    at = base
    for sha in todo:
        parent = git.first_parent(sha)
        if parent != at and (changes := keep(git.diff(at, parent))):
            open_changes(p4, git, parent, changes, ws)
            record(submit(p4, f"catch-up to {sha[:9]}"), "catch-up", sha, "", changes)
        at = parent
        changes = keep(git.diff(parent, sha))
        if not changes:
            print(f"skipping {sha[:9]}: nothing left after --exclude")
            continue
        subject = git.subject(sha)
        open_changes(p4, git, sha, changes, ws)
        desc = f"{subject} (upstream {sha[:9]})"
        if sha in shelved:
            record(shelve(p4, desc), "shelved", sha, subject, changes)
        else:
            record(submit(p4, desc), "commit", sha, subject, changes)
            at = sha
    with open(a.out, "w") as f:
        f.write("cl\tkind\tsha\tsubject\tc_files\tdirs\n")
        for row in rows:
            f.write("\t".join(str(x).replace("\t", " ") for x in row) + "\n")
    print(f"wrote {len(rows)} changelists to {a.out}")


if __name__ == "__main__":
    main()
