"""A fake OpenAI-compatible model for the e2e tests: canned, checked answers chosen by what the prompt asks for."""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CITES = [f"N{i}" for i in range(1, 80)] + [f"F{i}" for i in range(1, 20)]


PURPOSE = {   # the fixture's targets (serve-strong.sh): what each one's story is for
    "fw": ("UART driver counts transmit errors", "uart_send now counts transmit errors, so its callers see a new error value.",
           "Check that logger_flush handles the new -2.", "Does any caller retry a send after -2?"),
    "hal": ("HAL writes take an unsigned register", "hal_write now takes an unsigned register, so callers pass the new type.",
            "Check every caller of hal_write passes an unsigned register.", "Do any callers still pass a negative register?"),
}


def tier1_stories(user: str) -> dict:
    """One story per target, first piece first; a shared piece is put in the last target's story without the shared_code
    reason, so its check fails and it lands in Unsorted (the e2e tests look for it)."""
    cards = re.findall(r"^(P\d+)  [^·\n]+ · targets? ([^·\n]+?)( \(shared\))? · CL (\d+)", user, re.M)
    by_target: dict[str, list[str]] = {}
    shared = []
    for pid, targets, is_shared, _ in cards:
        if is_shared:
            shared.append(pid)
        else:
            by_target.setdefault(targets.split(", ")[0], []).append(pid)
    keys = {t: f"s{i}" for i, t in enumerate(sorted(by_target))}
    stories = []
    for t in sorted(by_target):
        title, purpose, check, question = PURPOSE.get(t, (f"Changes built for {t}", f"This changes the code built for {t}.",
                                                         "Check the changed functions' callers.", "Is any caller left behind?"))
        ids = by_target[t] + (shared if t == sorted(by_target)[-1] else [])
        stories.append({"key": keys[t], "title": title, "purpose": purpose, "check": [check], "questions": [question],
                        "related": [k for u, k in keys.items() if u != t],
                        "pieces": [{"id": p, "reason": "starts_purpose" if i == 0 else "same_feature",
                                    "evidence": [] if i == 0 else [ids[0]], "quote": []} for i, p in enumerate(ids)]})
    return {"action": "answer", "stories": stories, "unsorted": []}


def tier1_review(user: str) -> dict:
    """The new -2 is a hazard, the Uart::errors write needs a person to confirm, the rest is fine; each cites a node id or
    file:line from its own facts."""
    verdicts = []
    for block in re.split(r"\n\n(?=F\d+ \[)", user.split("FINDINGS:\n", 1)[1]):
        head = re.match(r"(F\d+) \[\w+\] ([\w_]+): (.*)", block)
        cite = re.search(r"\b(N\d+)\b|(\S+\.[ch]:\d+)", block.split("FACTS:", 1)[-1])
        if not head or not cite:
            continue
        title = head.group(3)
        verdict, reason = (("hazard", "logger_flush ignores the new -2, so a failed send goes unnoticed.")
                           if "new return value" in title else
                           ("needs_review", "uart_errors now reports what uart_send counts, so its readers see new values.")
                           if "Uart::errors" in title else ("no_hazard", "Every user of this change was updated with it."))
        verdicts.append({"finding": head.group(1), "verdict": verdict, "reason": reason, "cites": [cite.group(0)]})
    return {"action": "answer", "verdicts": verdicts}


def answer(system: str, user: str) -> dict:
    if "forming the stories of a change" in system:
        return {"related": [], "merge": []} if "STORIES (key | title" in user else tier1_stories(user)
    if "judging the risks of one story" in system:
        return tier1_review(user)
    if "Give each level" in user:
        return {"layers": []}
    if "Judge each side effect" in user:      # Uart::errors is the hazard; every other side effect is fine
        blocks = re.split(r"SIDE EFFECT (F\d+):", user)[1:]
        return {"verdicts": [{"finding": fid, "hazard": "Uart::errors" in body.split("\n", 2)[1], "cites": [],
                              "reason": "uart_errors assumes only uart_init writes Uart::errors." if "Uart::errors"
                              in body.split("\n", 2)[1] else "Nothing else depends on the value it writes."}
                             for fid, body in zip(blocks[::2], blocks[1::2])]}
    if "Summarize the whole change" in user:
        return {"summary": "The change adds transmit statistics to the UART driver.", "risk": "high", "cites": CITES}
    if "Describe this call flow" in user:
        return {"what": "The new -2 from uart_send reaches logger_flush, which drops it.", "title": "Flush drops the new error",
                "cites": CITES}
    if "Retell this change story" in user:
        return {"title": "uart_send's new error count reaches uart_errors",
                "summary": "uart_send now counts errors in Uart::errors, which uart_errors reports.", "cites": CITES}
    if "Explain the risk" in user:
        return {"explanation": "uart_send can now return -2, and logger_flush drops it.",
                "verify_steps": ["Check how logger_flush handles -2."], "hypotheses": []}
    if "Summarise this file" in user:
        path = re.search(r"FILE (\S+)", user)
        return {"summary": "This file now counts transmit errors.", "check": ["Check the readers of uart_errors."],
                "cites": [path.group(1)] if path else []}
    if "You are tortoise" in system:
        if "READ callers uart_send" not in user:
            return {"action": "read", "read": {"kind": "callers", "name": "uart_send"}, "why": "who handles -2"}
        return {"action": "answer", "text": "logger_flush drops the -2 that uart_send now returns.", "cites": CITES}
    return {}


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 — /v1/models, the health check
        self._send({"data": [{"id": "fake"}]})

    def do_POST(self):  # noqa: N802 — /v1/chat/completions
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req["messages"]
        out = answer(msgs[0]["content"], msgs[-1]["content"])
        self._send({"choices": [{"message": {"content": json.dumps(out)}}], "usage": {"prompt_tokens": 900, "completion_tokens": 60}})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
