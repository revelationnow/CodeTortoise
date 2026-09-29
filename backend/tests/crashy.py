"""Worker functions for crash-isolation tests (importable by process-pool workers via tests/ on sys.path)."""
import os

from codetortoise.facts.runner import _extract_with_fallback


def crash_on_uart(req):
    if req.file.endswith("uart.c"):
        os._exit(139)  # simulates libclang segfaulting on this TU
    return _extract_with_fallback(req)
