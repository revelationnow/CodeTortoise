"""The Health page says when the served pages were built from another commit than the server runs (owner feedback
2026-10-10: a pull without `npm run build` keeps serving old pages)."""
import json

from codetortoise.health import frontend_check

FIX = "cd frontend && npm ci && npm run build"


def test_pages_built_from_the_servers_commit_are_fine(tmp_path):
    (tmp_path / "build.json").write_text(json.dumps({"commit": "abc1234"}))
    c = frontend_check(tmp_path, "abc1234")
    assert (c.name, c.ok, c.hard) == ("frontend build", True, False)
    assert c.detail == "built from abc1234"


def test_pages_from_another_commit_or_without_a_build_stamp_say_how_to_rebuild(tmp_path):
    (tmp_path / "build.json").write_text(json.dumps({"commit": "old0001"}))
    c = frontend_check(tmp_path, "new0002")
    assert not c.ok and not c.hard
    assert c.detail == f"pages built from old0001, server runs new0002 — rebuild: {FIX}"
    (tmp_path / "build.json").unlink()
    assert frontend_check(tmp_path, "new0002").detail == f"pages built before build stamps (older than new0002) — rebuild: {FIX}"


def test_without_git_the_build_stamp_is_only_shown(tmp_path):
    (tmp_path / "build.json").write_text(json.dumps({"commit": "abc1234"}))
    c = frontend_check(tmp_path, None)
    assert c.ok and c.detail == "built from abc1234 (server commit unknown)"
