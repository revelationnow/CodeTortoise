/** Text with node ids shown as names (spec 2026-10-04-review-workspace §2.4): AI and template text cite `N4279`; the
 * reader sees `frame_pop`, linked to its code. */
import type { Names } from "../api";

export type Part = { text: string } | { code: string } | { node: string; label: string } | { finding: string };

const ID = /\b([NF]\d+)\b/;

function ids(segment: string, names: Names, findings: ReadonlySet<string>, plain: (s: string) => Part): Part[] {
  const out: Part[] = [];
  const add = (p: Part) => {                                   // an unknown finding number joins the text around it
    const last = out.at(-1);
    if (last && "text" in p && "text" in last) out[out.length - 1] = { text: last.text + p.text };
    else if (last && "code" in p && "code" in last) out[out.length - 1] = { code: last.code + p.code };
    else out.push(p);
  };
  segment.split(ID).forEach((p, i) => {
    if (i % 2 === 0) { if (p) add(plain(p)); }
    else if (p.startsWith("N")) add({ node: p, label: names[p]?.label ?? "a function" });
    else add(findings.has(p) ? { finding: p } : plain(p));
  });
  return out;
}

/** `findings`: the ids of this review's findings; any other F number is left as text. */
export function nameParts(text: string, names: Names, findings: Iterable<string>): Part[] {
  const known = new Set(findings);
  return text.split("`").flatMap((seg, i) => ids(seg, names, known, i % 2 ? (code) => ({ code }) : (t) => ({ text: t })));
}
