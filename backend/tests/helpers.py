from pathlib import Path

from codetortoise.config import Config
from codetortoise.services import build_services


def make_config(fx, data_dir: Path, **overrides) -> Config:
    raw = {
        "owner": "owner",
        "server": {"data_dir": str(data_dir), "public_url": "http://tortoise.local:8765"},
        "workspace": {"vcs": "git", "root": str(fx.root), "compile_commands": str(fx.compile_commands)},
        "auth": {"mode": "dev"},
        "analysis": {"module_min_files": 1, "workers": 1},
    }
    raw.update(overrides)
    return Config.model_validate(raw)


def make_services(fx, data_dir: Path, **kw):
    return build_services(make_config(fx, data_dir), **kw)
