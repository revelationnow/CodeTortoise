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


def threads(user: str) -> dict:
    """Each thread named after its first story, its first listed file its key file; the whole cites the first thread;
    connections keep their text."""
    rows = re.findall(r"^(T\d+) \|.*?\| (S\d+) ", user, re.M)
    first = dict(re.findall(r"^(T\d+) \|.*\n  files \(changed functions\): (\S+) \(", user, re.M))

    def pick(t: str) -> dict:
        f = first.get(t)
        return {"files": [f], "modules": [f.rsplit("/", 1)[0] + "/"] if "/" in f else []} if f else {}
    return {"threads": [{"id": t, "name": f"Thread of {sid}", "purpose": f"This thread holds {sid} and what builds on it.",
                         "cites": [sid], **pick(t)} for t, sid in rows],
            "whole": "The change reworks the UART driver and what calls it. Each thread says what it adds.",
            "whole_cites": [rows[0][0]] if rows else [], "connections": []}


def intro(user: str) -> dict:
    """Every part of the introduction, each citing what it introduces; the route keeps the threads' order."""
    body = user.split("THREAD DETAILS (id", 1)[1].split("CONNECTIONS (a", 1)[0]
    rows = re.findall(r"^(T\d+) \| ", body, re.M)
    first = dict(re.findall(r"^(T\d+) \|.*\n(?:  (?:modules|files): .*\n)*  stories: (S\d+) ", body, re.M))
    return {"whole": "The change reworks the UART driver. It spans the driver and the code that calls it. Each thread "
                     "below says what it adds. The main risk is a caller that misses a new result.",
            "whole_cites": rows[:1],
            "threads": [{"id": t, "intro": "This thread changes the UART driver. Its code sits in the driver. Its open "
                                           "checks say what to confirm.", "cites": [first.get(t, t)]} for t in rows],
            "route": [{"thread": t, "reason": "This thread comes next in the change.", "skim": False, "cites": [t]}
                      for t in rows]}


def account(user: str) -> dict:
    """A story's account (spec 2026-10-12-story-account-and-panels §1): purpose, one section per flow, effects."""
    cites = re.search(r"^CITE FROM: (.*)$", user, re.M).group(1).split(", ")[:1]
    flows = re.findall(r"^FLOW (FL\d+) \| ", user, re.M)
    return {"sections": [
        {"kind": "purpose", "flow": None, "cites": cites,
         "text": "This story makes uart_send count its transmit errors. You see the count through uart_errors."},
        *({"kind": "flow", "flow": f, "cites": cites,
           "text": "The caller reaches uart_send on this path. The new error count changes what it reports."} for f in flows),
        {"kind": "effects", "flow": None, "cites": cites,
         "text": "Code that reads Uart::errors now sees transmit errors too. Check the readers you own."}]}


def hypotheses(user: str) -> list[dict]:
    """The side effects a finding's explanation proposes: one, for the Uart::errors write, citing its first function; no
    other finding gets any, so only that finding's page shows a hypothesis."""
    title = re.search(r"^FINDING:\n\S+ \[\w+\] \w+: (.*)$", user, re.M)
    node = re.search(r"^nodes: \['(N\d+)'", user, re.M)
    if not (title and node and "Uart::errors" in title.group(1)):
        return []
    return [{"text": "Another reader of Uart::errors may see the count change between two reads.", "cites": [node.group(1)]}]


TITLES = ["A write longer than 64 bytes", "A write that fits", "Setting up the UART"]
LEADS = ["It follows a long write from `main` into `uart_send` and back.", "It follows a short write down to `hal_write`.",
         "It follows `uart_init` into the new `hal_write`."]


FALSE_CASES = {"len > 64": "Writes that fit (64 bytes or less)", "reg == REG_CTRL": "Writes to any other register"}


def design(user: str) -> dict:
    """The design overview's parts (spec 2026-11-02 §10): the verdict names the hazard, three concerns, three ownership
    lines, a title and a lead for each walk-through and each condition's false case; every part passes its checks. Its
    verdict says when the prompt carries a design context (spec 2026-11-02 §8). Some of its words are as long as a real
    model's: a long code span in the verdict, a long second concern and a long last ownership line, which cites a
    function by its node id (the overview shows its name)."""
    causes = re.findall(r"^(c[0-9a-f]{10}) \| (\w+) \|", user, re.M)
    hazard = next((c for c, kind in causes if kind == "hazard"), causes[0][0] if causes else None)
    confirm = next((c for c, kind in causes if kind == "confirm"), None)   # a kind the outline hides by default
    listed = re.findall(r"\b(S\d+) ", " ".join(re.findall(r"^  stories: (.*)$", user, re.M)))
    s1 = "S1" if "S1" in listed else listed[0] if listed else "S1"
    s2 = "S2" if "S2" in listed else s1
    path = "driver/uart.c" if "driver/uart.c" in user else s1
    walks, gates = re.findall(r"^(W\d+) \| ", user, re.M), re.findall(r"^(G\d+) \| (.+?) \| ", user, re.M)
    read = "DESIGN CONTEXT (from the review's owner):" in user
    node = re.search(r"^(N\d+) \| logger_flush \|", user, re.M) or re.search(r"^(N\d+) \| uart_send \|", user, re.M)
    verdict = ("The change holds together against its design context, but one new result goes unchecked. "
               if read else "The change holds together, but one new result goes unchecked. ")
    return {"verdict": verdict + "Settle whether `logger_flush` must handle the new -2 in "
                       "`g_logger.pending_lines_waiting_for_the_uart_to_drain`.",
            "verdict_causes": [hazard] if hazard else [],
            "concerns": [
                {"text": "Senders learn when a write is too long",
                 "how": "`uart_send` now returns -2 for a write longer than 64 bytes.", "stories": [s1],
                 "assessment": "confirm", "note": "`logger_flush` drops the -2.", "causes": [hazard] if hazard else []},
                {"text": "Register numbers stay unsigned through `HalRegisterBank::write_unsigned_register_value`",
                 "how": "`hal_write` now takes an unsigned register, so a caller that once passed -1 to mean the control "
                        "register now writes to register 4294967295 through "
                        "`HalRegisterBank::write_unsigned_register_value`.",
                 "stories": [s2], "assessment": "right",
                 "note": "Every caller in `driver/uart_register_map_for_the_second_channel.c` already passes a named register.",
                 "causes": []},
                {"text": "The error count stays readable", "how": "`uart_errors` reads the count that `uart_send` now writes.",
                 "stories": [s1, s2], "assessment": "note", "note": "", "causes": [confirm] if confirm else []}],
            "ownership": [
                {"tag": "right", "text": "The driver owns the length check.", "cites": [path]},
                {"tag": "questionable", "text": "The logger decides what a failed send means, and it drops the result.",
                 "cites": [s1]},
                {"tag": "shortfall", "text": "Nothing tells the caller of `logger_write` that a write was dropped, so a log "
                                             "line longer than 64 bytes leaves no trace in "
                                             "`Logger::pending_lines_waiting_for_the_uart_to_drain`.",
                 "cites": [node.group(1)] if node else [s1]}],
            "walks": [{"id": w, "title": TITLES[i] if i < len(TITLES) else f"Path {i + 1} through the change",
                       "lead": LEADS[i] if i < len(LEADS) else "It follows the call to where the change lands."}
                      for i, w in enumerate(walks)],
            "conditions": [{"id": g, "false_case": FALSE_CASES.get(test.strip(), "When the test does not hold")}
                           for g, test in gates]}


SHORT_VERDICT = "One new result goes unchecked. Settle whether `logger_flush` must handle the new -2."


def rewrite(user: str) -> dict:
    """A rewrite of one part (spec 2026-11-02 §10's AI menu): the verdict again, shorter when the reader's instruction
    asks for that; a walk-through's title and lead again. The rest is the design's answer, which a rewrite leaves unread."""
    out = design(user)
    asked = user.split("THE REVIEWER'S INSTRUCTION", 1)[1].lower() if "THE REVIEWER'S INSTRUCTION" in user else ""
    if "REWRITE: write the verdict again" in user and "fail the checks" in asked:
        out["verdict"] = "Too short."                      # an answer the verdict's checks refuse: the job fails
    elif "REWRITE: write the verdict again" in user:
        out["verdict"] = SHORT_VERDICT if "shorter" in asked else (
            "The change holds together once more, but one new result goes unchecked. "
            "Settle whether `logger_flush` must handle the new -2.")
    walk = re.search(r"REWRITE: write walk-through (W\d+)'s title", user)
    if walk:
        out["walks"] = [{"id": walk.group(1), "title": "A long write, told again",
                         "lead": "It follows a long write to where `uart_send` refuses it."}]
    return out


def answer(system: str, user: str) -> dict:
    if "REWRITE: write " in user:
        return rewrite(user)
    if "CHECKS BY CAUSE (id" in user:
        return design(user)
    if "THREAD DETAILS (id" in user:
        return intro(user)
    if "THREADS (id" in user:
        return threads(user)
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
    if "Write a reviewer's account" in user:
        return account(user)
    if "Retell this change story" in user:
        return {"title": "uart_send's new error count reaches uart_errors",
                "summary": "uart_send now counts errors in Uart::errors, which uart_errors reports.", "cites": CITES}
    if "Explain the risk" in user:
        return {"explanation": "uart_send can now return -2, and logger_flush drops it.",
                "verify_steps": ["Check how logger_flush handles -2."], "hypotheses": hypotheses(user)}
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
        content = json.dumps(answer(msgs[0]["content"], msgs[-1]["content"]))
        limit = req.get("max_tokens") or req.get("max_completion_tokens")
        if limit and limit < 2000:     # spec 2026-10-08-llm-robustness §9: a limit this low cuts the reply off
            self._send({"choices": [{"message": {"content": content[:len(content) // 2]}, "finish_reason": "length"}],
                        "usage": {"prompt_tokens": 900, "completion_tokens": limit}})
            return
        self._send({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 900, "completion_tokens": 60}})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
