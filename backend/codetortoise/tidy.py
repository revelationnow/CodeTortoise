"""Evidence written for people (spec 2026-10-07-review-reading §12): no Python reprs, counts that read as words, arrows as
arrows. Findings are stored as the detectors wrote them (their titles anchor comments and verdicts); text is tidied
where people and models read it. Code in backticks is left alone. frontend/src/lib/tidy.ts keeps the same rules."""
import re

_ITEM = r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|True|False|None"""
_CODE = r"(?<![\w\])}])"         # a bracket right after a name, `]`, `)` or `}` is a subscript or initialiser: code
_LIST = re.compile(rf"{_CODE}\[\s*((?:{_ITEM})(?:\s*,\s*(?:{_ITEM}))*)?\s*\]")
_DICT = re.compile(rf"{_CODE}\{{\s*((?:{_ITEM})\s*:\s*(?:{_ITEM})(?:\s*,\s*(?:{_ITEM})\s*:\s*(?:{_ITEM}))*)?\s*\}}")
_ONE = re.compile(_ITEM)
_COUNT = re.compile(r"\b(\d+) ((?:[A-Za-z_]+ )?[A-Za-z_]+)\(s\)( (?:reach|affect|call|use|need|read|write)\b)?")
_LISTED = re.compile(r"\b([A-Za-z_]+)\(s\) ([^;]+)")


def _plain(item: str) -> str:
    return item[1:-1] if item[:1] in "'\"" else item


def _items(body: str | None) -> list[str]:
    return [_plain(m.group(0)) for m in _ONE.finditer(body or "")]


def _list(m: re.Match) -> str:
    return ", ".join(_items(m.group(1))) or "none"


def _dict(m: re.Match) -> str:
    xs = _items(m.group(1))
    return ", ".join(f"{k} ({v})" for k, v in zip(xs[::2], xs[1::2], strict=True)) or "none"


def _count(m: re.Match) -> str:
    n, word, verb = int(m.group(1)), m.group(2), m.group(3) or ""
    if n != 1:
        return f"{n} {word}s{verb}"
    return f"1 {word}{verb + ('es' if verb.endswith(('ch', 'sh', 's', 'x')) else 's') if verb else ''}"


def _listed(m: re.Match) -> str:
    return f"{m.group(1)}{'s' if ',' in m.group(2) else ''} {m.group(2)}"


def _prose(text: str) -> str:
    text = text.replace(" -> ", " → ")
    text = _DICT.sub(_dict, _LIST.sub(_list, text))
    return _LISTED.sub(_listed, _COUNT.sub(_count, text))


def tidy(text: str, root: str | None = None) -> str:
    """`text` as a reader should see it, paths under the workspace `root` relative to it; the parts in backticks are code
    and stay as they are."""
    if root:
        text = text.replace(root.rstrip("/") + "/", "")
    parts = text.split("`")
    return "`".join(p if i % 2 else _prose(p) for i, p in enumerate(parts))
