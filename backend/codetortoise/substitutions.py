"""Repeated edits (spec 2026-10-04-change-stories §2.1): changed lines whose only difference is one run of tokens.

A pair of lines (one removed, one added, in the same hunk) is a substitution when, split into C tokens, they differ in
exactly one run of consecutive tokens: `git_vector_free` → `git_vector_dispose`. A function is explained by
substitutions when every changed line in it is part of such a pair.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_TOKEN = re.compile(r"""
    "(?:\\.|[^"\\])*"            # string literal
  | '(?:\\.|[^'\\])*'            # character literal
  | [A-Za-z_]\w*                 # identifier or keyword
  | \d[\w.]*                     # number
  | ->|\+\+|--|<<=|>>=|<<|>>|<=|>=|==|!=|&&|\|\||[-+*/%&|^]=|::|\.\.\.
  | \S                           # any other punctuation
""", re.X)
_COMMENT = re.compile(r"//.*$|/\*.*?\*/", re.S)


def tokens(line: str) -> list[str]:
    """C tokens of one line, comments and whitespace left out (a comment opened on the line runs to its end)."""
    code = _COMMENT.sub(" ", line)
    if "/*" in code:
        code = code[:code.index("/*")]
    return _TOKEN.findall(code)


@dataclass(frozen=True)
class Sub:
    old: str
    new: str


@dataclass(frozen=True)
class Site:
    """One substituted line pair: lines are 1-based in the before and after text."""
    sub: Sub
    before_line: int
    after_line: int
    before: str
    after: str


def substitution(old: str, new: str) -> Sub | None:
    """The one run of tokens that differs between two lines, or None (equal, or different in more than one place)."""
    a, b = tokens(old), tokens(new)
    ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    if len(ops) != 1 or ops[0][0] != "replace":    # equal, different in two places, or a token inserted or deleted
        return None
    _, i1, i2, j1, j2 = ops[0]
    return Sub(" ".join(a[i1:i2]), " ".join(b[j1:j2]))


def changed_pairs(before: list[str], after: list[str]) -> tuple[list[Site], int]:
    """Substituted line pairs between two texts (lists of lines), and how many changed lines were left unexplained."""
    sites, unexplained = [], 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace" or i2 - i1 != j2 - j1:
            unexplained += (i2 - i1) + (j2 - j1)
            continue
        for k in range(i2 - i1):
            s = substitution(before[i1 + k], after[j1 + k])
            if s is None:
                if tokens(before[i1 + k]) != tokens(after[j1 + k]):     # a whitespace-only change explains itself
                    unexplained += 2
                continue
            sites.append(Site(s, i1 + k + 1, j1 + k + 1, before[i1 + k].strip(), after[j1 + k].strip()))
    return sites, unexplained


def explained(before: list[str], after: list[str]) -> list[Site] | None:
    """The function's substitutions when every changed line is part of one, else None."""
    sites, unexplained = changed_pairs(before, after)
    return sites if sites and not unexplained else None
