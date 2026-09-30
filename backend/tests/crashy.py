"""Worker functions for crash-isolation tests (importable by process-pool workers via tests/ on sys.path)."""
import os

from codetortoise.facts.runner import _extract_with_fallback


def crash_on_uart(req):
    if req.file.endswith("uart.c"):
        os._exit(139)  # simulates libclang segfaulting on this TU
    return _extract_with_fallback(req)


def parse_crash_on_boom(path):
    from codetortoise.index.symbols import _parse_file
    if path.endswith("boom.c"):
        os._exit(139)  # simulates a native parser crash on this file
    return _parse_file(path)
