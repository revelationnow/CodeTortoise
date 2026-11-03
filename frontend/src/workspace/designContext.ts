/** The design context panel's pure parts (spec 2026-11-02 §8): the components as its text area holds them, the count of
 * what the prompts read, and the design's notes on the context as sentences. */
import type { DesignContext } from "../api";

export const EMPTY_CONTEXT: DesignContext = { notes: "", documents: [], conditions: { add: [], remove: [] }, components: [] };

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
