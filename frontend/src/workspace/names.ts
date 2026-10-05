/** Text with node ids shown as names (spec 2026-10-04-review-workspace §2.4): AI and template text cite `N4279`; the
 * reader sees `frame_pop`, linked to its code. */
import type { Names } from "../api";

export type Part = { text: string } | { code: string } | { node: string; label: string } | { finding: string };

const ID = /\b([NF]\d+)\b/;

function ids(segment: string, names: Names, plain: (s: string) => Part): Part[] {
  return segment.split(ID).flatMap((p, i): Part[] => {
    if (i % 2 === 0) return p ? [plain(p)] : [];
    return p.startsWith("N") ? [{ node: p, label: names[p]?.label ?? "a function" }] : [{ finding: p }];
  });
}

export function nameParts(text: string, names: Names): Part[] {
  return text.split("`").flatMap((seg, i) => ids(seg, names, i % 2 ? (code) => ({ code }) : (t) => ({ text: t })));
}
