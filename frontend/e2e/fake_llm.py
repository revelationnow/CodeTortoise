"""A fake OpenAI-compatible model for the e2e tests: canned, checked answers chosen by what the prompt asks for."""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CITES = [f"N{i}" for i in range(1, 80)] + [f"F{i}" for i in range(1, 20)]


def answer(system: str, user: str) -> dict:
    if "Give each level" in user:
        return {"layers": []}
    if "Summarize the whole change" in user:
        return {"summary": "The change adds transmit statistics to the UART driver.", "risk": "high", "cites": CITES}
    if "Describe this call flow" in user:
        return {"what": "The new -2 from uart_send reaches logger_flush, which drops it.", "title": "Flush drops the new error",
                "cites": CITES}
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
