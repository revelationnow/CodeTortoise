"""Perforce Source: shelved (pending) and submitted CLs, read-only against the base workspace."""
from __future__ import annotations

from codetortoise.paths import canon
from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, SourceFile, stack
from codetortoise.vcs.p4runner import P4Error, P4Runner
from codetortoise.vcs.source import MAX_SOURCE_BYTES, SourceBinary, SourceError, SourceNotAllowed, SourceTooLarge

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

    def _print(self, spec: str, warnings: list[str]) -> str:
        try:
            return self.p4.print_text(spec)
        except P4Error as e:
            warnings.append(f"{spec}: content unavailable ({e})")
            return ""

    def _files(self, cl: int, d: dict, shelved: bool, warnings: list[str]) -> list[FileChange]:
        depots, actions, revs = _indexed(d, "depotFile"), _indexed(d, "action"), _indexed(d, "rev")
        types = _indexed(d, "type")
        where: dict[str, str] = {}
        for r in (self.p4.run("where", *depots) if depots else []):
            if "unmap" not in r and r.get("depotFile") and r.get("path"):  # "-//..." exclusion lines carry unmap
                where.setdefault(r["depotFile"], r["path"])
        out = []
        for i, depot in enumerate(depots):
            action = actions[i]
            rev = int(revs[i]) if i < len(revs) and revs[i].isdigit() else 0
            binary = i < len(types) and "binary" in types[i]
            base_rev = rev if shelved else rev - 1
            before = after = ""
            if not binary:
                if action not in _NO_BEFORE and base_rev > 0:
                    before = self._print(f"{depot}#{base_rev}", warnings)
                if action not in _NO_AFTER:
                    after = self._print(f"{depot}@={cl}" if shelved else f"{depot}#{rev}", warnings)
            local = where.get(depot)
            if not local:
                warnings.append(f"{depot}: not in client view of the base workspace (shown, not analysed)")
            out.append(FileChange(depot=depot, local=canon(local) if local else "", action=action, before=before,
                                  after=after, base_rev=f"#{base_rev}" if base_rev > 0 else None))
        return out

    def _drift(self, files: list[FileChange]) -> list[DriftItem]:
        out = []
        for f in files:
            if f.base_rev is None or not f.local:
                continue
            try:
                recs = self.p4.run("have", f.depot)
                actual = f"#{recs[0].get('haveRev')}" if recs else "not synced"
            except P4Error:
                actual = "not synced"
            if actual != f.base_rev:
                out.append(DriftItem(depot=f.depot, local=f.local, expected=f.base_rev, actual=actual))
        return out

    def depots_for(self, locals_: list[str]) -> dict[str, str]:
        if not locals_:
            return {}
        out = {}
        for r in self.p4.run("where", *locals_):
            if "unmap" not in r and r.get("path") and r.get("depotFile"):
                out.setdefault(canon(r["path"]), r["depotFile"])
        return {p: out[p] for p in locals_ if p in out}

    def read(self, depot: str) -> SourceFile:
        """Unchanged file at the base workspace's have revision; refuses anything outside the client view."""
        try:
            recs = self.p4.run("fstat", "-T", "depotFile,clientFile,haveRev,headType", depot)
        except P4Error as e:
            raise SourceNotAllowed(f"{depot}: {e}") from e
        rec = recs[0] if recs else {}
        if not rec.get("clientFile") or not rec.get("haveRev"):
            raise SourceNotAllowed(f"{depot}: not synced in the base workspace")
        if any(t in rec.get("headType", "") for t in ("binary", "apple", "resource")):
            raise SourceBinary(f"{depot}: binary file")
        try:
            text = self.p4.print_text(f"{depot}#{rec['haveRev']}")
        except P4Error as e:
            raise SourceNotAllowed(f"{depot}: {e}") from e
        if len(text.encode("utf-8", errors="replace")) > MAX_SOURCE_BYTES:
            raise SourceTooLarge(f"{depot}: too large")
        return SourceFile(depot=depot, local=canon(rec["clientFile"]), rev=f"#{rec['haveRev']}", text=text)

    def load(self, cls: list[int]) -> ChangeSet:
        per_cl, metas, warnings = [], [], []
        try:
            for cl in sorted(set(cls)):
                meta, d, shelved = self._describe(cl)
                metas.append(meta)
                per_cl.append((meta, self._files(cl, d, shelved, warnings)))
            files = stack(per_cl)
            return ChangeSet(cls=metas, files=files, drift=self._drift(files), warnings=warnings)
        except P4Error as e:
            raise SourceError(str(e)) from e
