"""Command line: serve, index, review (headless), stories-check, fixture-demo."""
from __future__ import annotations

import argparse
import ipaddress
import logging
import sys
from pathlib import Path

import yaml

from codetortoise.config import ConfigError, ServerConfig, load_config


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def plain_http_warning(server: ServerConfig) -> str | None:
    """The startup warning for plain HTTP reachable beyond this machine (spec §14.2), or None."""
    if server.tls_cert is not None or _loopback(server.host):
        return None
    return (f"Serving plain HTTP on {server.host}:{server.port} — logins (Perforce passwords) and source code cross the "
            "network unencrypted. Set server.tls_cert/tls_key, or bind 127.0.0.1.")


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
    srv = svc.cfg.server
    warning = plain_http_warning(srv)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)
        logging.warning(warning)
    uvicorn.run(app, host=srv.host, port=srv.port,
                ssl_certfile=str(srv.tls_cert) if srv.tls_cert else None,
                ssl_keyfile=str(srv.tls_key) if srv.tls_key else None)
    return 0


def cmd_index(args) -> int:
    svc = _services(args.config)
    n = svc.build_index(full=args.full)
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


def cmd_stories_check(args) -> int:
    from codetortoise.stories_check import stories_check
    svc = _services(args.config)
    try:
        return stories_check(svc, args.review, args.runs)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1


def cmd_init(args) -> int:
    from codetortoise.init_config import render, scan, summary
    from codetortoise.vcs.p4runner import P4Runner
    out = Path(args.out).resolve()
    if out.exists() and not args.force:
        print(f"{out} exists; use --force to replace it", file=sys.stderr)
        return 1

    def client_root(port: str, client: str) -> str | None:
        recs = P4Runner(port, client, args.p4_bin, timeout=30, cwd=args.root).run("client", "-o", client)
        return recs[0].get("Root") if recs else None
    s = scan(Path(args.root), client_root=None if args.no_p4 else client_root)
    out.write_text(render(s))
    print(summary(s, out))
    return 0


def cmd_check_parse(args) -> int:
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.runner import run_extraction
    svc = _services(args.config)
    tc = svc.toolchain
    tc.prepare()
    file = str(Path(args.file).resolve())
    info = tc.explain(file)
    e = info["entry"]
    if e is None:
        print(f"{file}: no compile entry in any database ({len(svc.cdb.databases)} loaded); "
              "it parses with default flags only")
    else:
        g = info["group"]
        how = "exact" if info["exact"] else "borrowed from the nearest file in the same database"
        print(f"compile entry: {e.file} ({how})\n  directory: {e.directory}\n  database: {e.db}")
        for o in info["others"]:
            print(f"  also in: {o.db} (ignored: the first entry wins)")
        if info["override"] is not None:
            print(f"  override: {info['override'].match}")
        print(f"compiler: {g.compiler}" + (f" (query failed: {g.error})" if g.error else ""))
        print(f"target: {g.target or 'from the command or the host'}")
        lib = g.libclang
        rd = f", resource dir {lib.resource_dir}" if lib.resource_dir else ""
        print(f"libclang: {lib.path or 'bundled'} ({lib.reason}){rd}")
        print("arguments: " + " ".join(info["args"]))
        if svc.cdb.problems:
            print("database problems: " + "; ".join(svc.cdb.problems[:5]))
    args_ = tc.args_for(file)
    lib_path = tc.libclang_for(file).path
    [facts] = run_extraction([TuRequest(file=file, args=args_, variant="after", libclang=lib_path)], lib_path, 1)
    t = facts.tu
    result = "tree-sitter fallback" if t.extractor == "treesitter" else t.confidence
    print(f"result: {result} ({t.error_count} error(s))")
    if t.stripped_flags:
        print("stripped flags: " + " ".join(t.stripped_flags))
    for d in t.diagnostics[:20]:
        print(f"  {d}")
    print("functions: " + (", ".join(f.qualname for f in facts.functions) or "none"))
    return 0 if t.extractor == "clang" else 1


def cmd_fetch_libclang(args) -> int:
    from codetortoise.toolchain.libclang import DEFAULT_VERSION, fetch_libclang
    cfg = load_config(Path(args.config))
    args.version = args.version or DEFAULT_VERSION
    try:
        dest = fetch_libclang(cfg.server.data_dir, version=args.version, source=args.source, sha256=args.sha256)
    except (RuntimeError, OSError) as e:
        print(f"fetch-libclang: {e}", file=sys.stderr)
        return 1
    print(f"installed libclang {args.version} in {dest}; CodeTortoise uses it unless tortoise.yaml names another")
    return 0


def cmd_fixture_demo(args) -> int:
    from codetortoise.fixture import build_fixture
    from codetortoise.fixture_large import build_large_fixture
    dest = Path(args.dir).resolve()
    fx = build_large_fixture(dest) if args.large else build_fixture(dest)
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
    s = sub.add_parser("index", help="bring the symbol index up to date (only changed files are parsed again)")
    s.add_argument("--config", required=True)
    s.add_argument("--full", action="store_true", help="parse every file again")
    s.set_defaults(fn=cmd_index)
    s = sub.add_parser("review", help="run a review headless and print findings")
    s.add_argument("--config", required=True)
    s.add_argument("--title")
    s.add_argument("cls", nargs="+", type=int)
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("stories-check", help="run tier 1's stories N times on a review and print how often they agree")
    s.add_argument("--config", required=True)
    s.add_argument("review", type=int)
    s.add_argument("--runs", type=int, default=3)
    s.set_defaults(fn=cmd_stories_check)
    s = sub.add_parser("init", help="write a starter tortoise.yaml for the workspace you are in")
    s.add_argument("--root", default=".", help="a folder inside the workspace (default: the current folder)")
    s.add_argument("--out", default="tortoise.yaml")
    s.add_argument("--force", action="store_true", help="replace an existing file")
    s.add_argument("--p4-bin", default="p4")
    s.add_argument("--no-p4", action="store_true", help="do not ask Perforce for the client's Root")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("check-parse", help="show how one file is parsed, and why it fails if it does")
    s.add_argument("--config", required=True)
    s.add_argument("file")
    s.set_defaults(fn=cmd_check_parse)
    s = sub.add_parser("fetch-libclang", help="install a newer libclang from the official LLVM release")
    s.add_argument("--config", required=True)
    s.add_argument("--version", default=None)
    s.add_argument("--from", dest="source", help="an LLVM-<version>-Linux-<arch>.tar.xz already downloaded")
    s.add_argument("--sha256", help="the archive's SHA-256 (needed for versions without a pinned digest)")
    s.set_defaults(fn=cmd_fetch_libclang)
    s = sub.add_parser("fixture-demo", help="create a demo workspace + config from the bundled fixture")
    s.add_argument("--dir", required=True)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--llm-base-url")
    s.add_argument("--llm-model", default="gpt-4o-mini")
    s.add_argument("--large", action="store_true", help="a generated project whose CLs 201+202 need several boards")
    s.set_defaults(fn=cmd_fixture_demo)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
