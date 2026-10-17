import { describe, expect, it } from "vitest";
import { cardText, connectionRows, testsLine } from "./overview";
import type { Connection, TestsRow, Thread } from "./types";

const thread = (id: string, name = id): Thread => ({ id, name, purpose: "", text_source: "template", stories: [], cls: [], open_checks: 0 });
const conn = (a: string, b: string, kind: Connection["kind"] = "caller", shown = true, text = `${a}–${b}`): Connection =>
  ({ a, b, kind, text, facts: [], shown });
const T = ["T1", "T2", "T3", "T4"].map((id) => thread(id));

describe("how the threads connect", () => {
  it("says each shown connection as a sentence row", () => {
    const rows = connectionRows(T, [conn("T1", "T2", "caller", true, "both run inside `main`"),
                                    conn("T2", "T4", "bundled", true, "nothing besides arriving in CL 104"),
                                    conn("T1", "T3", "place", false)]);
    expect(rows).toEqual([{ text: "A and B: both run inside `main`", bundled: false },
                          { text: "B and D: nothing besides arriving in CL 104 — ask the author", bundled: true }]);
  });
});

describe("the Tests row", () => {
  const tests = (covers: string[], untested: string[]): TestsRow => ({ stories: ["S9"], functions: 6, covers, untested });
  it("says which threads the tests cover and which nothing tests", () => {
    expect(testsLine(tests(["T1", "T2"], ["T3"]), T)).toBe("Tests: 6 cover threads A and B · nothing tests C");
    expect(testsLine(tests(["T1"], []), T)).toBe("Tests: 6 cover thread A");
    expect(testsLine(tests([], ["T1", "T2", "T3"]), T)).toBe("Tests: 6 · nothing tests A, B and C");
  });
});


describe("a thread card's text", () => {
  const t = (over: Partial<Thread>): Thread => ({ ...thread("T1"), purpose: "Sends bytes.", ...over });

  it("shows the strong model's intro alone: it says what the thread does", () => {
    expect(cardText(t({ intro: "Mine. Two. Three.", intro_source: "llm", text_source: "llm" })))
      .toEqual([{ text: "Mine. Two. Three.", ai: true }]);
  });

  it("keeps the purpose above a fixed intro, labelled AI when the model wrote it", () => {
    expect(cardText(t({ intro: "1 story. Nothing is open.", intro_source: "template", text_source: "llm" })))
      .toEqual([{ text: "Sends bytes.", ai: true }, { text: "1 story. Nothing is open.", ai: false }]);
  });

  it("shows only the purpose on a reading stored before the introduction", () => {
    expect(cardText(t({}))).toEqual([{ text: "Sends bytes.", ai: false }]);
  });
});
