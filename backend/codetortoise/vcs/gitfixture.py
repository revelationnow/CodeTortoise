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
