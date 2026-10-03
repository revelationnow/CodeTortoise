"""Each toolchain group parses with its own library, given that library's built-in headers."""
import json

from codetortoise.config import ToolchainConfig, ToolchainOverride
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain


def _ws(tmp_path):
    ws = tmp_path / "ws"
    for f in ("m4/a.c", "dsp/c.c"):
        (ws / f).parent.mkdir(parents=True, exist_ok=True)
        (ws / f).write_text("int f(void) { return 0; }\n")
    cc = ws / "compile_commands.json"
    cc.write_text(json.dumps([{"directory": str(ws), "file": f, "arguments": ["/no/cc", "-c", f]}
                              for f in ("m4/a.c", "dsp/c.c")]))
    return ws, load_databases(cc, ws, None)


def _fake_lib(root, version):
    lib = root / "lib" / f"libclang.so.{version}"
    (root / "lib" / "clang" / version.split(".")[0] / "include").mkdir(parents=True)
    lib.write_bytes(b"")
    return lib


def test_an_override_gives_its_files_their_own_library_and_resource_dir(tmp_path):
    ws, db = _ws(tmp_path)
    hexlib = _fake_lib(tmp_path / "hexagon", "19.1.0")
    tc = Toolchain(ToolchainConfig(overrides=[{"match": "dsp/**", "libclang": str(hexlib)}]), db, tmp_path / "d" / "tc",
                   root=ws)
    tc.prepare()                                                     # loads the default (bundled) library here
    assert tc.libclang_for(str(ws / "m4/a.c")).kind == "bundled"
    dsp = tc.libclang_for(str(ws / "dsp/c.c"))
    assert (dsp.path, dsp.kind) == (str(hexlib), "explicit")
    args = tc.args_for(str(ws / "dsp/c.c"))
    assert args[args.index("-resource-dir") + 1] == str(tmp_path / "hexagon" / "lib" / "clang" / "19")
    assert "-resource-dir" not in tc.args_for(str(ws / "m4/a.c"))      # the bundled library finds its own


def test_a_fetched_library_is_used_and_its_resource_dir_passed(tmp_path):
    ws, db = _ws(tmp_path)
    fetched = _fake_lib(tmp_path / "d" / "libclang" / "23.1.2", "23.1.2")
    tc = Toolchain(ToolchainConfig(), db, tmp_path / "d" / "tc", root=ws)
    choice = tc.libclang_for(str(ws / "m4/a.c"))
    assert (choice.path, choice.kind) == (str(fetched), "fetched")
    args = tc.args_for(str(ws / "m4/a.c"))
    assert args[args.index("-resource-dir") + 1] == str(tmp_path / "d" / "libclang" / "23.1.2" / "lib" / "clang" / "23")


def test_the_facts_stage_runs_each_librarys_files_in_their_own_workers(fx, tmp_path, monkeypatch):
    from codetortoise import pipeline
    from tests.helpers import make_services
    svc = make_services(fx, tmp_path)
    lib = _fake_lib(tmp_path / "vendor", "17.0.6")
    svc.cfg.toolchain.overrides = [ToolchainOverride(match="driver/**", libclang=str(lib))]
    calls = []
    real = pipeline.run_extraction

    def spy(reqs, libclang_path, workers, *a, **k):
        calls.append((libclang_path, sorted(r.file.split("/")[-1] for r in reqs)))
        return real(reqs, None, workers, *a, **k) if libclang_path is None else []
    monkeypatch.setattr(pipeline, "run_extraction", spy)
    rid = svc.store.create_review("t", "owner", [101])
    pipeline.run_review(rid, svc)
    libs = {path for path, _ in calls}
    assert libs == {None, str(lib)}
    assert all(files == ["uart.c"] for path, files in calls if path == str(lib))
