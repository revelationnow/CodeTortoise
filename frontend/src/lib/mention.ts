/** The @ menu in comment boxes (spec 2026-10-03 §6): what is being typed, what to offer, what to insert. */

export const TORTOISE = "tortoise";

export interface MentionOption { name: string; detail: string; disabled: boolean; ai: boolean }

/** The @word ending at the caret (start: the @'s index), or null when the caret isn't in one. */
export function mentionQuery(text: string, caret: number): { start: number; query: string } | null {
  const m = /(^|\s)@(\w*)$/.exec(text.slice(0, caret));
  return m ? { start: caret - m[2].length - 1, query: m[2] } : null;
}

/** @tortoise first (greyed with the reason when it can't run), then the review's people; narrowed by the query. */
export function mentionOptions(query: string, people: string[], ai: { ok: boolean; detail: string }): MentionOption[] {
  const q = query.toLowerCase();
  const all: MentionOption[] = [{ name: TORTOISE, detail: ai.detail, disabled: !ai.ok, ai: true },
    ...[...new Set(people)].filter((p) => p !== TORTOISE).map((p) => ({ name: p, detail: "", disabled: false, ai: false }))];
  return all.filter((o) => o.name.toLowerCase().startsWith(q));
}

/** Replace text[start, caret) with "@name " (no extra space when one follows); the caret goes after it. */
export function insertMention(text: string, start: number, caret: number, name: string): { text: string; caret: number } {
  const rest = text.slice(caret), gap = /^\s/.test(rest) ? "" : " ";
  const head = `${text.slice(0, start)}@${name}${gap}`;
  return { text: head + rest, caret: head.length + (gap ? 0 : 1) };
}
