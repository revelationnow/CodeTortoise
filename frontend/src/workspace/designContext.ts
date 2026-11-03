/** The design context panel's pure parts (spec 2026-11-02 §8): the components as its text area holds them, the count of
 * what the prompts read, and the design's notes on the context as sentences. */
import type { DesignContext } from "../api";

export const EMPTY_CONTEXT: DesignContext = { notes: "", documents: [], conditions: { add: [], remove: [] }, components: [] };

/** What the server's DesignContext holds (design_context.py): characters the prompts read, then how many of each list,
 * and a document's name. */
export const CAP = 12_000;
export const MAX = { documents: 10, add: 10, remove: 20, components: 30 } as const;
const NAME_MAX = 200;

const cut = (s: string, n: number) => [...s].slice(0, n).join("");

/** A file's name as its document's name: trimmed, and cut to what a name holds. */
export const docName = (name: string): string => cut(name.trim(), NAME_MAX);

/** A link's document's name (final review I4): the last segment of its path with its query, read (`%20` a space), or its
 * host when it has no path; cut to what a name holds, as a wiki page's address is often longer. */
export function linkName(link: string): string {
  const raw = link.trim();
  let u: URL;
  try { u = new URL(raw); } catch { return docName(raw); }
  const text = (u.pathname.split("/").filter(Boolean).pop() ?? u.host) + u.search;
  try { return docName(decodeURIComponent(text)); } catch { return docName(text); }
}

/** A line per component: its name, a colon, its globs. */
export const componentsText = (cs: DesignContext["components"]): string =>
  cs.map((c) => `${c.name}: ${c.globs.join(", ")}`).join("\n");

/** The text area's components; a line without a name or a glob is `bad`, said back as written (trimmed). */
export function parseComponents(text: string): { components: DesignContext["components"]; bad: string[] } {
  const components: DesignContext["components"] = [], bad: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const i = line.indexOf(":"), name = i < 0 ? "" : line.slice(0, i).trim();
    const globs = i < 0 ? [] : line.slice(i + 1).split(",").map((g) => g.trim()).filter(Boolean);
    if (name && globs.length) components.push({ name, globs });
    else bad.push(line);
  }
  return { components, bad };
}

/** The characters the prompts read of the context, counted as the server counts them (`context_text`): the notes, then
 * each document as "DOCUMENT name:" and its text, a blank line between; characters, not UTF-16 units. */
export function contextChars(c: DesignContext): number {
  const parts = [c.notes.trim(), ...c.documents.filter((d) => d.text.trim()).map((d) => `DOCUMENT ${d.name.trim()}:\n${d.text.trim()}`)]
    .filter(Boolean);
  return [...parts.join("\n\n")].length;
}

/** A note of the design on its context ("the condition `x` is not in the changed functions") as a sentence. */
export const noteSentence = (note: string): string => `${note.charAt(0).toUpperCase()}${note.slice(1)}.`;
