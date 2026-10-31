"""A workspace's bundle on a server of many (spec 2026-10-31 §6): shared store, ledger and AI pool; its own folder and
store-entry keys; its own libclang even when the process loaded another."""
import threading

from helpers import make_config, make_services

from codetortoise.config import ToolchainConfig
from codetortoise.llm.ledger import Ledger
from codetortoise.pipeline import AiPool, JobRunner
from codetortoise.services import build_services
from codetortoise.sinks import marks, set_mark
from codetortoise.store import Store
from codetortoise.toolchain import libclang as lc
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain


def test_bundles_share_the_store_and_ledger_and_keep_their_index_toolchain_and_entries_apart(fx, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    cfg = make_config(fx, data)
    store = Store(data / "tortoise.db")
    ledger = Ledger(store, cfg.llm.budget)
    a = build_services(cfg, store=store, ledger=ledger, home=data / "workspaces" / "1", scope="ws1")
    b = build_services(cfg, store=store, ledger=ledger, home=data / "workspaces" / "2", scope="ws2")
    assert a.store is b.store is store and a.ledger is b.ledger is ledger
    assert a.index.db_path == data / "workspaces" / "1" / "symbols.db"
    assert a.toolchain.work_dir == data / "workspaces" / "1" / "toolchain"
    assert a.toolchain.data_dir == data                     # where fetch-libclang puts libraries
    a.remember_stripped(["-mfoo"])
    assert store.kv_get("strip_flags:ws1") == ["-mfoo"] and store.kv_get("strip_flags:ws2") is None
    assert build_services(cfg, store=store, ledger=ledger, home=data / "workspaces" / "1",
                          scope="ws1").toolchain.strip >= {"-mfoo"}
    a.build_index()
    a.layers.get()
    keys = [r["key"] for r in store._all("SELECT key FROM kv WHERE key LIKE 'layers:%'")]
    assert keys and all(":ws1:" in k for k in keys)


def test_a_bundle_built_on_its_own_keeps_the_single_workspace_folders_and_keys(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    assert svc.index.db_path == tmp_path / "symbols.db" and svc.toolchain.data_dir == tmp_path
    svc.remember_stripped(["-mbar"])
    assert svc.store.kv_get(f"strip_flags:{fx.root}") == ["-mbar"]


def test_shared_sink_marks_are_kept_per_workspace(tmp_path):
    store = Store(tmp_path / "t.db")
    set_mark(store, "Uart::errors", True, "ws1")
    assert marks(store, "ws1") == ["Uart::errors"] and marks(store, "ws2") == [] and marks(store) == []
    assert store.kv_get("sink_marks:ws1") == ["Uart::errors"]
    set_mark(store, "log_t::buf", True)
    assert store.kv_get("sink_marks") == ["log_t::buf"]                 # a bundle on its own: the one entry, as before


def test_the_library_this_process_has_is_described_in_place(monkeypatch):
    bundled = lc.LibclangInfo(path="/b/libclang.so", version="clang version 1", vendor=False)
    monkeypatch.setattr(lc, "_loaded", bundled)
    assert lc.library_info(None) is bundled
    vendor = lc.LibclangInfo(path="/v/libclang.so.19", version="clang version 19", vendor=True)
    monkeypatch.setattr(lc, "_loaded", vendor)
    assert lc.library_info("/v/libclang.so.19") is vendor


def test_a_toolchain_that_picks_another_library_than_the_process_has_still_prepares(monkeypatch, tmp_path):
    vendor = lc.LibclangInfo(path="/v/libclang.so.19", version="clang version 19", vendor=True)
    monkeypatch.setattr(lc, "_loaded", vendor)        # another workspace's toolchain loaded its own library here
    tc = Toolchain(ToolchainConfig(), CompileDb([]), tmp_path / "tc", data_dir=tmp_path)
    tc.prepare()                                      # chooses the bundled library: described from a worker process
    assert tc.choice.kind == "bundled" and tc.libclang.vendor is False
    assert tc.libclang.path != vendor.path and tc.libclang.version.startswith("clang version")
    assert lc._loaded is vendor                       # this process keeps the library it has


def test_queues_share_one_ai_pool_and_its_jobs(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    pool = AiPool(2)
    a, b = JobRunner(svc, pool), JobRunner(svc, pool)
    done = threading.Event()
    job = a.submit_ai(7, "amy", "flow", "FL1", done.set)
    assert done.wait(10) and b.ai_jobs[7] == [job] and job["id"] == 1
    assert b.submit_ai(7, "bob", "flow", "FL2", lambda: None)["id"] == 2     # ids count per review, across queues


def test_a_queue_is_busy_while_a_review_or_an_index_build_waits_or_runs(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    reviews = JobRunner(svc)                            # not started: what is submitted waits
    assert reviews.busy() is None
    reviews.submit_review(svc.store.create_review("t", "owner", [101]))
    assert reviews.busy() == "a review is running in this workspace; try again when it finishes"
    index = JobRunner(svc)
    index.submit_index()
    assert index.busy() == "the symbol index is being built in this workspace; try again when it finishes"
    index.start()
    index.stop()
    index._thread.join(60)
    assert index.busy() is None
