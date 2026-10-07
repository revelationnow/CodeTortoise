/** A Markdown line as plain text, for places that show one line of a CL description (the rail, a CL's heading): block
 * markers, emphasis, code ticks and link targets go; snake_case and spaced-out `a * b` stay. */
export function plainTitle(line: string): string {
  let s = line.trim();
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
