/** Evidence written for people (spec 2026-10-07-review-reading §12): the rules of backend/codetortoise/tidy.py, for the
 * finding text the server sends as the detectors wrote it (its titles anchor comments, so they are tidied only here). */

const ITEM = String.raw`'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|True|False|None`;
const CODE = String.raw`(?<![\w\])}])`; // a bracket right after a name, `]`, `)` or `}` is a subscript or initialiser: code
const LIST = new RegExp(String.raw`${CODE}\[\s*((?:${ITEM})(?:\s*,\s*(?:${ITEM}))*)?\s*\]`, "g");
const DICT = new RegExp(String.raw`${CODE}\{\s*((?:${ITEM})\s*:\s*(?:${ITEM})(?:\s*,\s*(?:${ITEM})\s*:\s*(?:${ITEM}))*)?\s*\}`, "g");
const ONE = new RegExp(ITEM, "g");
const COUNT = /\b(\d+) ((?:[A-Za-z_]+ )?[A-Za-z_]+)\(s\)( (?:reach|affect|call|use|need|read|write)\b)?/g;
const LISTED = /\b([A-Za-z_]+)\(s\) ([^;]+)/g;

const items = (body: string | undefined) => [...(body ?? "").matchAll(ONE)].map(([m]) => (/^['"]/.test(m) ? m.slice(1, -1) : m));

function prose(text: string): string {
  return text.replaceAll(" -> ", " → ")
    .replace(LIST, (_, body) => items(body).join(", ") || "none")
    .replace(DICT, (_, body) => {
      const xs = items(body);
      return xs.filter((_, i) => i % 2 === 0).map((k, i) => `${k} (${xs[2 * i + 1]})`).join(", ") || "none";
    })
    .replace(COUNT, (_, n: string, word: string, verb = "") =>
      n !== "1" ? `${n} ${word}s${verb}` : `1 ${word}${verb && verb + (/(ch|sh|s|x)$/.test(verb) ? "es" : "s")}`)
    .replace(LISTED, (_, word: string, rest: string) => `${word}${rest.includes(",") ? "s" : ""} ${rest}`);
}

/** `text` as a reader should see it; the parts in backticks are code and stay as they are. */
export function tidy(text: string): string {
  return text.split("`").map((p, i) => (i % 2 ? p : prose(p))).join("`");
}

/** "3 files", "1 flow"; an empty count is never shown (""). */
export function counted(n: number, noun: string): string {
  return n ? `${n} ${noun}${n === 1 ? "" : "s"}` : "";
}
