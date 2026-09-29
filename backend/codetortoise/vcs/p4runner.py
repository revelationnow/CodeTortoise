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
        # severity >= 3 is a failure; lower severities (e.g. "file(s) not in client view") are warnings
        errors = [d.get("data", "").strip() for d in records
                  if d.get("code") == "error" and int(d.get("severity", 3)) >= 3]
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

    def login_check(self, user: str, password: str, all_hosts: bool = False) -> str:
        """Validates credentials. Returns the ticket (printed, not stored in the tickets file).

        all_hosts=True (`-a`) yields a host-unlocked ticket; needed for the owner, whose ticket is presented
        to Swarm from a different host than the one it was issued on.
        """
        cmd = self._base(user) + ["login", "-p"] + (["-a"] if all_hosts else [])
        try:
            r = subprocess.run(cmd, input=(password + "\n").encode(),
                               capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise P4Error(f"p4 login: {e}") from e
        if r.returncode != 0:
            raise P4Error("p4 login failed: " + (r.stderr or r.stdout).decode(errors="replace").strip())
        lines = [l.strip() for l in r.stdout.decode(errors="replace").splitlines() if l.strip()]
        return lines[-1] if lines else ""
