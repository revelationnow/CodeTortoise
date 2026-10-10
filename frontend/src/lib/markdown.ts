/** A Markdown line as plain text, for places that show one line of a CL description (the rail, a CL's heading): HTML
 * tags, block markers, emphasis, code ticks and link targets go and entities are decoded; snake_case and spaced-out
 * `a * b` stay. */
export function plainTitle(line: string): string {
  let s = decodeEntities(line.replace(/<\/?[A-Za-z][^>]*>/g, "")).trim();
  for (let prev = ""; prev !== s;) {
    prev = s;
    s = s.replace(/^(#{1,6}\s+|>\s*|[-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+)/, "");
  }
  return s
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/(\*\*|__)(\S(?:.*?\S)?)\1/g, "$2")
    .replace(/~~(\S(?:.*?\S)?)~~/g, "$1")
    .replace(/\*(\S(?:.*?\S)?)\*/g, "$1")
    .replace(/(^|\W)_(\S(?:.*?\S)?)_(?=\W|$)/g, "$1$2")
    .trim();
}

/** A CL description as its first line and the rest. The rest loses the indent all its lines share (a CL template or a
 * habit of indenting under the title), which Markdown would otherwise read as code or as one paragraph. */
export function descriptionParts(desc: string): { title: string; body: string } {
  const lines = desc.replace(/\r\n?/g, "\n").split("\n");
  while (lines.length && !lines[0].trim()) lines.shift();
  const [title = "", ...rest] = lines;
  const shared = rest.filter((l) => l.trim()).map((l) => l.match(/^[ \t]*/)![0])
    .reduce<string | null>((a, b) => { if (a === null) return b; let i = 0; while (i < a.length && a[i] === b[i]) i++; return a.slice(0, i); }, null) ?? "";
  const body = rest.map((l) => (l.startsWith(shared) ? l.slice(shared.length) : l.trimStart())).join("\n");
  return { title: title.trim(), body: body.replace(/^\s*\n/, "").trimEnd() };
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'", nbsp: " " };

/** `&amp;`, `&lt;`, `&#39;`, `&#x27;` … as the characters they stand for; unknown names stay as written. */
export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e: string) => {
    if (e[0] !== "#") return ENTITIES[e.toLowerCase()] ?? m;
    const n = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
    return Number.isFinite(n) && n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : m;
  });
}

const LIST = /^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]+|$)/;
const BLOCK_TAGS = "div|p|details|summary|blockquote|table|thead|tbody|tr|td|th|ul|ol|li|center|section|h[1-6]";
const BLOCK_OPEN = new RegExp(`^\\s*<(${BLOCK_TAGS})\\b[^>]*>\\s*$`, "i");
const BLOCK_CLOSE = new RegExp(`^\\s*</(${BLOCK_TAGS})>\\s*$`, "i");
const width = (ws: string) => [...ws].reduce((n, c) => n + (c === "\t" ? 4 - (n % 4) : 1), 0);

/** A CL description as Markdown reads it the way its author meant (owner feedback 2026-10-10): indented bullets are a
 * list (nested by their relative indent) set off from the text around them; other indented lines are text, not code
 * (Perforce forms indent with tabs; code belongs in ``` fences, kept as written); an HTML block tag on its own line is
 * set off by blank lines so the Markdown inside it renders. Line breaks are kept by the renderer (remark-breaks). */
export function prepareMarkdown(text: string): string {
  const out: string[] = [];
  let fence: { mark: string; indent: number } | null = null;
  let levels: number[] = [];                       // indent widths of the bullets in the current list
  const gap = () => { if (out.length && out[out.length - 1].trim()) out.push(""); };
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    const f = line.match(/^([ \t]*)(`{3,}|~{3,})/);
    if (fence) {
      const lead = line.match(/^[ \t]*/)![0];
      out.push(width(lead) >= fence.indent ? line.slice(Math.min(lead.length, fence.indent)) : line.trimStart());
      if (f && f[2][0] === fence.mark[0] && f[2].length >= fence.mark.length && !line.slice(f[0].length).trim()) fence = null;
      continue;
    }
    if (!line.trim()) { out.push(""); continue; }
    if (f) {
      if (!levels.length) gap();
      fence = { mark: f[2], indent: f[1].length };
      out.push(line.trimStart());
      continue;
    }
    const m = line.match(LIST);
    if (m) {
      const w = width(m[1]);
      if (!levels.length) gap();
      while (levels.length && levels[levels.length - 1] > w) levels.pop();
      if (!levels.length || levels[levels.length - 1] < w) levels.push(w);
      out.push("    ".repeat(levels.length - 1) + line.slice(m[1].length));
      continue;
    }
    if (levels.length && /^[ \t]/.test(line)) { out.push(line.trimStart()); continue; }   // an item's wrapped text
    if (levels.length) { levels = []; gap(); }                                        // the list ends
    if (BLOCK_OPEN.test(line) || BLOCK_CLOSE.test(line)) { gap(); out.push(line.trim(), ""); continue; }
    out.push(line.trimStart());
  }
  return out.join("\n");
}
