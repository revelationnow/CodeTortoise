"""lab/p4-import.py builds a Perforce history from a git project (spec 2026-10-03-large-change-boards §7)."""
import csv
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "lab" / "p4-import.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def write(repo: Path, path: str, text: str | bytes, exe: bool = False) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text if isinstance(text, bytes) else text.encode())
    p.chmod(0o755 if exe else 0o644)


@pytest.fixture
def project(tmp_path):
    """A base, a small commit, a large one (31 new C files in two directories, a rename, a delete, a binary, an
    executable bit dropped, a file with '@' in its name edited) and a small one to shelve."""
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q", "-b", "main")
    git(src, "config", "user.email", "lab@example.com")
    git(src, "config", "user.name", "lab")
    for i in range(5):
        write(src, f"src/a/f{i}.c", f"int f{i}(void) {{ return {i}; }}\n")
    write(src, "include/x.h", "int f0(void);\n")
    write(src, "tests/test_a.c", "int test_a(void) { return 0; }\n")
    write(src, "tests/resources/blob.bin", b"\0\1\2")
    write(src, "tools/run.sh", "#!/bin/sh\necho run\n", exe=True)
    write(src, "docs/readme.txt", "hello\n")
    base = commit(src, "base")
    write(src, "src/a/f0.c", "int f0(void) { return 10; }\n")
    (src / "docs/readme.txt").unlink()
    write(src, "src/a/at@sign.c", "int at(void) { return 1; }\n")
    small = commit(src, "small: tidy f0")
    for i in range(16):
        write(src, f"src/b/g{i}.c", f"int g{i}(void) {{ return {i}; }}\n")
    for i in range(15):
        write(src, f"src/c/h{i}.c", f"int h{i}(void) {{ return {i}; }}\n")
    write(src, "include/x.h", "int f0(void);\nint g0(void);\n")
    git(src, "mv", "src/a/f2.c", "src/c/moved.c")
    (src / "src/a/f3.c").unlink()
    write(src, "src/b/logo.png", b"\x89PNG\r\n\x1a\n\0\0\0binary")
    write(src, "tools/run.sh", "#!/bin/sh\necho run\n")
    write(src, "src/a/at@sign.c", "int at(void) { return 2; }\n")
    write(src, "tests/resources/blob.bin", b"\0\1\2\3")
    large = commit(src, "large: add the b and c modules")
    write(src, "src/b/g0.c", "int g0(void) { return 100; }\n")
    write(src, "src/d/new.c", "int nw(void) { return 0; }\n")
    (src / "src/a/f1.c").unlink()
    shelved = commit(src, "shelved: try g0 = 100")
    return src, base, small, large, shelved


def run(*args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=300)


def test_list_picks_first_parent_commits_touching_enough_c_files_outside_tests(project):
    src, base, small, large, shelved = project
    r = run("--repo", str(src), "--base", base, "--end", "main", "--list")
    assert r.returncode == 0, r.stderr
    rows = [line.split("\t") for line in r.stdout.strip().splitlines()]
    assert [row[0] for row in rows] == [large[:9]]
    assert rows[0][1:3] == ["36", "4"]                           # C files outside tests, their directories
    r = run("--repo", str(src), "--base", base, "--end", "main", "--list", "--min-files", "1")
    assert [line.split("\t")[0] for line in r.stdout.strip().splitlines()] == [small[:9], large[:9], shelved[:9]]


needs_p4d = pytest.mark.skipif(not (shutil.which("p4d") and shutil.which("p4")), reason="p4 and p4d are not on PATH")


@needs_p4d
def test_import_into_a_throwaway_p4d_with_catch_up_and_a_shelve(project, tmp_path):
    src, base, small, large, shelved = project
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = f"127.0.0.1:{s.getsockname()[1]}"
    root, ws, out = tmp_path / "p4root", tmp_path / "ws", tmp_path / "cls.tsv"
    env = {k: v for k, v in os.environ.items() if not k.startswith("P4")} | {"P4USER": "lab", "P4TICKETS": str(tmp_path / "t")}
    try:
        r = run("--repo", str(src), "--base", base, "--end", "main", "--depot", "//depot/proj", "--workspace", str(ws),
                "--client", "proj-ws", "--port", port, "--root", str(root), "--exclude", "tests/resources",
                "--shelve", shelved[:9], "--out", str(out), env=env)
        assert r.returncode == 0, r.stdout + r.stderr

        def p4(*a: str) -> str:
            return subprocess.run(["p4", "-p", port, "-c", "proj-ws", *a], check=True, capture_output=True, text=True,
                                  env=env).stdout

        # by client: a change holding only shelved files matches no depot path
        changes = p4("-ztag", "-F", "%change%\t%status%\t%desc%", "changes", "-l", "-c", "proj-ws").splitlines()
        changes = [c for c in changes if c.strip()]                    # a long description ends in a blank line
        assert [c.split("\t", 2)[1:] for c in reversed(changes)] == [
            ["submitted", f"import at upstream {base[:9]}"],
            ["submitted", f"catch-up to {large[:9]}"],
            ["submitted", f"large: add the b and c modules (upstream {large[:9]})"],
            ["pending", f"shelved: try g0 = 100 (upstream {shelved[:9]})"]]
        heads = dict(line.split("\t") for line in
                     p4("-ztag", "-F", "%depotFile%\t%headAction%", "fstat", "//depot/proj/...").strip().splitlines())
        assert heads["//depot/proj/docs/readme.txt"] == "delete" and heads["//depot/proj/src/a/f2.c"] == "delete"
        assert heads["//depot/proj/src/c/moved.c"] == "add" and heads["//depot/proj/src/a/at%40sign.c"] == "edit"
        assert not any("tests/resources" in f for f in heads) and "//depot/proj/tests/test_a.c" in heads
        assert p4("print", "-q", "//depot/proj/include/x.h") == "int f0(void);\nint g0(void);\n"
        assert p4("print", "-q", "//depot/proj/src/a/at%40sign.c") == "int at(void) { return 2; }\n"
        types = lambda f: p4("-ztag", "-F", "%headType%", "fstat", f).strip()      # noqa: E731
        assert "binary" in types("//depot/proj/src/b/logo.png")
        mods = lambda f: types(f).partition("+")[2]                                # noqa: E731
        assert "x" in mods("//depot/proj/tools/run.sh#1") and "x" not in mods("//depot/proj/tools/run.sh")
        pending = changes[0].split("\t")[0]
        files = re.findall(r"^\.\.\. (//\S+)#\d+ (\w+)", p4("describe", "-S", "-s", pending), re.M)
        assert sorted(f"{f}\t{act}" for f, act in files) == sorted(
            ["//depot/proj/src/b/g0.c\tedit", "//depot/proj/src/d/new.c\tadd", "//depot/proj/src/a/f1.c\tdelete"])
        assert p4("opened").strip() == "" and not (ws / "src/d/new.c").exists() and (ws / "src/a/f1.c").exists()
        assert not (ws / "docs").exists() and not (ws / "src/d").exists()    # no empty directories left behind
        rows = list(csv.DictReader(out.open(), delimiter="\t"))
        assert [(r_["kind"], r_["sha"]) for r_ in rows] == [("base", base[:9]), ("catch-up", large[:9]),
                                                             ("commit", large[:9]), ("shelved", shelved[:9])]
        assert [r_["cl"] for r_ in rows] == [c.split("\t")[0] for c in reversed(changes)]
        assert rows[2]["c_files"] == "36" and rows[2]["dirs"] == "4" and rows[2]["subject"] == "large: add the b and c modules"
        again = run("--repo", str(src), "--base", base, "--depot", "//depot/proj", "--workspace", str(tmp_path / "ws2"),
                    "--client", "proj-ws2", "--port", port, env=env)
        assert again.returncode != 0 and "already has files" in again.stderr
    finally:
        pid = root / "p4d.pid"
        if pid.exists():
            os.kill(int(pid.read_text()), signal.SIGTERM)
