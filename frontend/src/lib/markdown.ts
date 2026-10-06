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
