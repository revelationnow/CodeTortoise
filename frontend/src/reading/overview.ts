/** The overview's connection sentences, Tests row and thread blocks (spec 2026-10-16-outline-and-causes §3). */
import { letter } from "./checks";
import type { Connection, TestsRow, Thread } from "./types";

/** "A and B: both run inside `main`", one per shown connection: the tile on a phone, where arcs do not fit. */
export function connectionRows(threads: Thread[], conns: Connection[]): { text: string; bundled: boolean }[] {
  const name = new Map(threads.map((t, i) => [t.id, letter(i, t.id)]));
  return conns.filter((k) => k.shown && name.has(k.a) && name.has(k.b)).map((k) => ({
    text: `${name.get(k.a)} and ${name.get(k.b)}: ${k.text}${k.kind === "bundled" ? " — ask the author" : ""}`,
    bundled: k.kind === "bundled",
  }));
}

/** "A", "A and B", "A, B and C". */
export function listed(xs: string[]): string {
  return xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

/** "Tests: 6 cover threads A and B · nothing tests C". */
export function testsLine(t: TestsRow, threads: Thread[]): string {
  const name = new Map(threads.map((th, i) => [th.id, letter(i, th.id)]));
  const of = (ids: string[]) => listed(ids.map((id) => name.get(id) ?? id));
  return `Tests: ${t.functions}${t.covers.length ? ` cover thread${t.covers.length === 1 ? "" : "s"} ${of(t.covers)}` : ""}`
    + (t.untested.length ? ` · nothing tests ${of(t.untested)}` : "");
}

/** A thread card's paragraphs: the strong model's intro alone (it says what the thread does), else the purpose above the
 * fixed intro, so a card never loses the sentence that says what its thread does. */
export function cardText(t: Thread): { text: string; ai: boolean }[] {
  if (t.intro && t.intro_source === "llm") return [{ text: t.intro, ai: true }];
  return [...(t.purpose ? [{ text: t.purpose, ai: t.text_source === "llm" }] : []), ...(t.intro ? [{ text: t.intro, ai: false }] : [])];
}
