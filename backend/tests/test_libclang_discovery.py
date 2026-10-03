"""Which libclang each file uses, and fetching a newer one (spec 2026-10-02 toolchains §5)."""
import hashlib
import io
import tarfile

import pytest

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.libclang import fetch_libclang, find_libclang


def _lib(path, version="21"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    (path.parent / "clang" / version / "include").mkdir(parents=True, exist_ok=True)
    return path


def test_discovery_order_and_reasons(tmp_path):
    vendor = _lib(tmp_path / "vendor" / "lib" / "libclang.so.17")
    (tmp_path / "vendor" / "bin").mkdir()
    (tmp_path / "vendor" / "bin" / "clang").write_text("")
    search = tmp_path / "tools"
    _lib(search / "llvm-19" / "lib" / "libclang.so.19.1.0", "19")
    _lib(search / "llvm-22" / "lib" / "libclang.so.22.1.1", "22")
    fetched = _lib(tmp_path / "data" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2", "23")
    system = _lib(tmp_path / "usr" / "lib" / "llvm-20" / "lib" / "libclang-20.so.1", "20")
    systems = [str(tmp_path / "usr" / "lib" / "llvm-*" / "lib")]
    explicit = _lib(tmp_path / "x" / "libclang.so")

    def find(cfg, compiler=None, override=None):
        return find_libclang(cfg, compiler=compiler, override=override, data_dir=tmp_path / "data", system_globs=systems)

    c = find(ToolchainConfig(libclang=str(explicit)), compiler=str(tmp_path / "vendor/bin/clang"))
    assert (c.path, c.kind) == (str(explicit), "explicit")
    c = find(ToolchainConfig(), compiler=str(tmp_path / "vendor/bin/clang"))
    assert (c.path, c.kind) == (str(vendor), "toolchain") and "next to" in c.reason
    c = find(ToolchainConfig(search_paths=[str(search)]), compiler="/usr/bin/gcc")       # gcc ships no libclang
    assert c.path.endswith("libclang.so.22.1.1") and c.kind == "search"                 # newest in the search paths
    assert c.resource_dir == str(search / "llvm-22" / "lib" / "clang" / "22")
    c = find(ToolchainConfig())
    assert (c.path, c.kind) == (str(fetched), "fetched")
    (tmp_path / "data" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2").unlink()
    c = find(ToolchainConfig())
    assert (c.path, c.kind) == (str(system), "system")
    c = find_libclang(ToolchainConfig(), data_dir=tmp_path / "none", system_globs=[])
    assert (c.path, c.kind, c.resource_dir) == (None, "bundled", None) and "bundled" in c.reason
    c = find(ToolchainConfig(libclang=str(explicit)), override=str(vendor))
    assert (c.path, c.kind) == (str(vendor), "explicit")                                  # an override's library


def _tarball(tmp_path, top="LLVM-23.1.2-Linux-X64"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in [(f"{top}/lib/libclang.so.23.1.2", b"ELF"), (f"{top}/lib/clang/23/include/stddef.h", b"x"),
                           (f"{top}/bin/clang-23", b"big"), (f"{top}/lib/libLLVM.so", b"big")]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f"{top}/lib/libclang.so")
        link.type, link.linkname = tarfile.SYMTYPE, "libclang.so.23.1.2"
        tar.addfile(link)
    p = tmp_path / f"{top}.tar.xz"
    p.write_bytes(buf.getvalue())
    return p, hashlib.sha256(buf.getvalue()).hexdigest()


def test_fetch_from_a_file_keeps_only_libclang_and_its_headers(tmp_path):
    tar, digest = _tarball(tmp_path)
    dest = fetch_libclang(tmp_path / "data", version="23.1.2", source=str(tar), sha256=digest)
    assert dest == tmp_path / "data" / "libclang" / "23.1.2"
    kept = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file() or p.is_symlink())
    assert kept == ["lib/clang/23/include/stddef.h", "lib/libclang.so", "lib/libclang.so.23.1.2"]


def test_a_checksum_mismatch_keeps_nothing(tmp_path):
    tar, _ = _tarball(tmp_path)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        fetch_libclang(tmp_path / "data", version="23.1.2", source=str(tar), sha256="0" * 64)
    assert not (tmp_path / "data" / "libclang" / "23.1.2").exists()


def test_an_unknown_file_needs_a_checksum(tmp_path):
    tar, _ = _tarball(tmp_path)
    with pytest.raises(RuntimeError, match="--sha256"):
        fetch_libclang(tmp_path / "data", version="9.9.9", source=str(tar))


def test_unsafe_paths_in_the_archive_are_refused(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        info = tarfile.TarInfo("LLVM-23.1.2-Linux-X64/lib/../../../evil/libclang.so.1")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    p = tmp_path / "evil.tar.xz"
    p.write_bytes(buf.getvalue())
    with pytest.raises(RuntimeError, match="unsafe path"):
        fetch_libclang(tmp_path / "data", version="23.1.2", source=str(p), sha256=hashlib.sha256(buf.getvalue()).hexdigest())
    assert not (tmp_path / "evil").exists()


def test_the_fetch_command_installs_from_a_file(tmp_path, capsys):
    import yaml

    from codetortoise.cli import main
    tar, digest = _tarball(tmp_path)
    cfg = tmp_path / "t.yaml"
    cfg.write_text(yaml.safe_dump({"owner": "o", "workspace": {"vcs": "git", "root": str(tmp_path), "compile_commands": "x"},
                                   "server": {"data_dir": str(tmp_path / "data")}}))
    assert main(["fetch-libclang", "--config", str(cfg), "--from", str(tar), "--sha256", digest]) == 0
    assert (tmp_path / "data" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2").exists()
    assert "installed libclang 23.1.2" in capsys.readouterr().out
    assert main(["fetch-libclang", "--config", str(cfg), "--from", str(tar), "--sha256", "0" * 64]) == 1


SYSTEM21 = "/usr/lib/llvm-21/lib/libclang-21.so.1"


@pytest.mark.skipif(not __import__("os").path.exists(SYSTEM21), reason="needs a system LLVM 21")
def test_files_parse_in_workers_with_a_newer_library(fx):
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.runner import run_extraction
    from codetortoise.toolchain.compile_db import CompileDb, sanitize_args
    db = CompileDb.load(fx.compile_commands)
    reqs = [TuRequest(file=e.file, args=sanitize_args(e) + ["-resource-dir", "/usr/lib/llvm-21/lib/clang/21"],
                      variant="after", libclang=SYSTEM21) for e in db.entries]
    facts = run_extraction(reqs, SYSTEM21, workers=2)
    assert len(facts) == len(reqs) and all(f.tu.extractor == "clang" and f.tu.confidence == "precise" for f in facts)
    assert sum(len(f.functions) for f in facts) == 13
