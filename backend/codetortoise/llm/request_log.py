"""The request log (spec 2026-10-08-llm-robustness §7, §8): each HTTP request to a model, kept as `llm.request_log`
says, compressed, and pruned after `llm.request_log_days`."""
from __future__ import annotations

import io
import json
import zipfile
import zlib
from datetime import UTC, datetime, timedelta

from codetortoise.store import Store

_COLS = ("seq", "sent_at", "elapsed_ms", "url", "model", "status", "error", "stop_reason", "truncated", "repair",
         "max_output_tokens", "prompt_tokens", "completion_tokens")


def keep(mode: str, failed: bool, records: list[dict]) -> bool:
    """Whether a call's records are written: `all` always, `failed` when the call failed or a reply was cut off or
    repaired, `off` never."""
    if mode == "off" or not records:
        return False
    return mode == "all" or failed or any(r["truncated"] or r["repair"] for r in records)


def write(store: Store, call_id: int, rid: int | None, records: list[dict]) -> None:
    sql = (f"INSERT INTO llm_requests(call_id, review_id, {', '.join(_COLS)}, request, response) "
           f"VALUES({','.join('?' * (len(_COLS) + 4))})")
    for r in records:
        store._exec(sql, (call_id, rid, *[int(r[c]) if c in ("truncated", "repair") else r[c] for c in _COLS],
                          zlib.compress(json.dumps(r["request"]).encode()),
                          zlib.compress(r["response"].encode()) if r["response"] is not None else None))


def prune(store: Store, days: int, now: datetime | None = None) -> int:
    """Deletes the requests sent more than `days` before `now`; returns how many."""
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat(timespec="seconds")
    return store._exec("DELETE FROM llm_requests WHERE sent_at < ?", (cutoff,)).rowcount


def rows(store: Store, rid: int, call: int | None = None) -> list[dict]:
    """The review's logged requests (one call's with `call`), in call and send order, decoded."""
    sql = ("SELECT r.*, c.purpose, c.target FROM llm_requests r JOIN llm_calls c ON c.id = r.call_id "
           "WHERE r.review_id=?" + (" AND r.call_id=?" if call is not None else "") + " ORDER BY r.call_id, r.seq")
    out = []
    for d in store._all(sql, (rid,) if call is None else (rid, call)):
        d["request"] = json.loads(zlib.decompress(d["request"])) if d["request"] is not None else None
        d["response"] = zlib.decompress(d["response"]).decode() if d["response"] is not None else None
        d["truncated"], d["repair"] = bool(d["truncated"]), bool(d["repair"])
        out.append(d)
    return out


def _parsed(text: str | None):
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def files(got: list[dict]) -> dict[str, bytes]:
    """One JSON file per request: `call-<id>/<seq>.json` with its metadata, request and response."""
    return {f"call-{r['call_id']}/{r['seq']}.json": json.dumps(
        {**{k: r[k] for k in ("call_id", "purpose", "target", *_COLS)}, "request": r["request"],
         "response": _parsed(r["response"])}, indent=2).encode() for r in got}


def zip_bytes(got: list[dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files(got).items():
            z.writestr(name, data)
    return buf.getvalue()


def _dash(v) -> str:
    return "-" if v is None else str(v)


def line(r: dict) -> str:
    """One request on one line: call, purpose, target, model, seq, status, stop reason, limit, tokens, ms, error."""
    err = f" {r['error'][:80]}" if r["error"] else ""
    return (f"call {r['call_id']} {r['purpose']} {r['target']} {r['model']} #{r['seq']} {_dash(r['status'])} "
            f"{_dash(r['stop_reason'])} limit={_dash(r['max_output_tokens'])} "
            f"tokens={_dash(r['prompt_tokens'])}+{_dash(r['completion_tokens'])} {_dash(r['elapsed_ms'])}ms{err}")
