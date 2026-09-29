"""Command line: serve, index, review (headless), fixture-demo."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from codetortoise.config import ConfigError, load_config


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
    uvicorn.run(app, host=svc.cfg.server.host, port=svc.cfg.server.port)
    return 0


def cmd_index(args) -> int:
    svc = _services(args.config)
    n = svc.build_index()
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


def cmd_fixture_demo(args) -> int:
    from codetortoise.fixture import build_fixture
    dest = Path(args.dir).resolve()
    fx = build_fixture(dest)
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
    s = sub.add_parser("index", help="(re)build the repo-wide symbol index")
    s.add_argument("--config", required=True)
    s.set_defaults(fn=cmd_index)
    s = sub.add_parser("review", help="run a review headless and print findings")
    s.add_argument("--config", required=True)
    s.add_argument("--title")
    s.add_argument("cls", nargs="+", type=int)
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("fixture-demo", help="create a demo workspace + config from the bundled fixture")
    s.add_argument("--dir", required=True)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--llm-base-url")
    s.add_argument("--llm-model", default="gpt-4o-mini")
    s.set_defaults(fn=cmd_fixture_demo)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
