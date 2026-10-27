import { describe, expect, it } from "vitest";
import { cardText, foldTitles, overviewHeading, sectionConnections, startButton, testsLine, threadAction,
  threadCounts } from "./overview";
import type { BuildImpact, Cause, Connection, Mark, SinkHit, TestsRow, Thread } from "./types";

const thread = (id: string, name = id, stories: string[] = []): Thread =>
  ({ id, name, purpose: "", text_source: "template", stories, cls: [], open_checks: 0 });
const conn = (a: string, b: string, kind: Connection["kind"] = "caller", shown = true, text = `${a}–${b}`): Connection =>
  ({ a, b, kind, text, facts: [], shown });
const T = ["T1", "T2", "T3", "T4"].map((id) => thread(id));

describe("the overview's heading and start button (spec 2026-10-25-review-ui-redesign §5.1)", () => {
  it("counts the threads, and says the change when there are none", () => {
    expect(overviewHeading(0)).toBe("The change");
    expect(overviewHeading(1)).toBe("1 thread");
    expect(overviewHeading(5)).toBe("5 threads");
  });

  const r = { order: ["S2", "S1", "S3", "S9"], threads: [thread("T1", "a", ["S2", "S1"]), thread("T2", "b", ["S3"])] };

  it("names the thread of the first story in reading order before anything is read", () => {
    expect(startButton(r, new Set())).toEqual({ sid: "S2", label: "Start with Thread A ›" });
    expect(startButton({ ...r, order: ["S3", "S2", "S1", "S9"] }, new Set())).toEqual({ sid: "S3", label: "Start with Thread B ›" });
  });

  it("says Start here when the first story is in no thread, or there are no threads", () => {
    expect(startButton({ order: ["S9", "S2"], threads: r.threads }, new Set())).toEqual({ sid: "S9", label: "Start here ›" });
    expect(startButton({ order: ["S1"], threads: [] }, new Set())).toEqual({ sid: "S1", label: "Start here ›" });
  });

  it("continues at the first unread story once one is read, whichever it was", () => {
    expect(startButton(r, new Set(["S2"]))).toEqual({ sid: "S1", label: "Continue ›" });
    expect(startButton(r, new Set(["S1"]))).toEqual({ sid: "S2", label: "Continue ›" });
  });

  it("has no button when every story is read or there are none", () => {
    expect(startButton(r, new Set(["S2", "S1", "S3", "S9"]))).toBeNull();
    expect(startButton({ order: [], threads: [] }, new Set())).toBeNull();
  });

  it("still says Start while the only stories read are ones the reading no longer has", () => {
    // ticks outlive a re-run: a story gone from the order is no reason to say Continue
    expect(startButton(r, new Set(["S77"]))).toEqual({ sid: "S2", label: "Start with Thread A ›" });
    expect(startButton(r, new Set(["S77", "S3"]))).toEqual({ sid: "S2", label: "Continue ›" });
  });
});

describe("a thread section's action and counts (§5.2)", () => {
  it("starts at the first story, continues at the first unread one, and is done when all are read", () => {
    expect(threadAction(["S2", "S1"], new Set())).toEqual({ kind: "start", sid: "S2" });
    expect(threadAction(["S2", "S1"], new Set(["S2"]))).toEqual({ kind: "continue", sid: "S1" });
    expect(threadAction(["S2", "S1"], new Set(["S1"]))).toEqual({ kind: "continue", sid: "S2" });
    expect(threadAction(["S2", "S1"], new Set(["S1", "S2"]))).toEqual({ kind: "done" });
    expect(threadAction([], new Set())).toBeNull();
  });

  const cause = (id: string, threadId: string | null, kind: Cause["kind"], places: string[]): Cause =>
    ({ id, kind, thread: threadId, story: null, text: id, places, flows: [], finding: null, change: null });
  const mark = (key: string, changed = false): Mark => ({ key, user: "ann", at: "2026-10-25T09:00:00Z", source_line: "", changed });
  const t = thread("T1", "a", ["S1", "S2", "S3"]);

  it("counts the thread's shown causes still open and the stories the reader has read", () => {
    const causes = [cause("c1", "T1", "caller", ["k1"]), cause("c2", "T1", "reader", ["k2", "k3"]),
                    cause("c3", "T1", "confirm", ["k4"]), cause("c4", "T2", "caller", ["k5"]), cause("c5", "T1", "result", ["k6"])];
    const marks = { k1: mark("k1"), k2: mark("k2"), k6: mark("k6", true) };
    // c1 is marked; c2 still has k3; c3's kind is hidden; c4 is another thread's; c5's line changed since its mark
    expect(threadCounts(t, causes, new Set(["confirm"]), marks, new Set(["S2", "S9"]))).toEqual({ stories: 3, open: 2, read: 1 });
  });

  it("has no open count on a reading stored before causes", () => {
    expect(threadCounts(t, null, new Set(), {}, new Set())).toEqual({ stories: 3, open: null, read: 0 });
    expect(threadCounts(t, undefined, new Set(), {}, new Set())).toEqual({ stories: 3, open: null, read: 0 });
  });

  it("counts none open, not an unknown count, on a reading whose causes are an empty list", () => {
    expect(threadCounts(t, [], new Set(), {}, new Set())).toEqual({ stories: 3, open: 0, read: 0 });
  });
});

describe("how the threads connect, under the later thread (§5.2)", () => {
  it("puts each shown connection under the later of its two threads, naming the earlier one", () => {
    const rows = sectionConnections(T, [conn("T1", "T2", "caller", true, "both run inside `main`"),
                                        conn("T4", "T2", "bundled", true, "nothing besides arriving in CL 104"),
                                        conn("T1", "T3", "place", false),
                                        conn("T3", "T1", "vocabulary", true, "both use `hal_write`"),
                                        conn("T1", "T9", "caller", true, "a thread the reading no longer has")]);
    expect([...rows.entries()]).toEqual([
      ["T2", [{ before: "With Thread A: ", text: "both run inside `main`", after: "", ai: false, bundled: false }]],
      ["T4", [{ before: "With Thread B: ", text: "nothing besides arriving in CL 104", after: " — ask the author", ai: false, bundled: true }]],
      ["T3", [{ before: "With Thread A: ", text: "both use `hal_write`", after: "", ai: false, bundled: false }]],
    ]);
  });

  it("keeps every connection under one thread, in the order given", () => {
    const rows = sectionConnections(T, [conn("T4", "T2", "bundled", true, "nothing besides arriving in CL 104"),
                                        conn("T1", "T3", "caller", true, "both run inside `main`"),
                                        conn("T4", "T3", "vocabulary", true, "both use `hal_write`")]);
    expect([...rows.entries()]).toEqual([
      ["T4", [{ before: "With Thread B: ", text: "nothing besides arriving in CL 104", after: " — ask the author", ai: false, bundled: true },
              { before: "With Thread C: ", text: "both use `hal_write`", after: "", ai: false, bundled: false }]],
      ["T3", [{ before: "With Thread A: ", text: "both run inside `main`", after: "", ai: false, bundled: false }]],
    ]);
  });

  it("marks the words of a connection the strong model reworded, and only its own words: not the thread prefix or the author note", () => {
    const rows = sectionConnections(T, [{ ...conn("T1", "T2", "caller", true, "both start up from `main`"), text_source: "llm" },
                                        { ...conn("T2", "T3", "bundled", true, "only together in CL 104"), text_source: "llm" },
                                        { ...conn("T1", "T4", "caller", true, "both run inside `main`"), text_source: "template" },
                                        conn("T3", "T4", "vocabulary", true, "both use `hal_write`")]);   // a reading stored before the source has none
    expect([...rows.values()].flat().map((r) => [r.before, r.text, r.after, r.ai])).toEqual([
      ["With Thread A: ", "both start up from `main`", "", true],
      ["With Thread B: ", "only together in CL 104", " — ask the author", true],
      ["With Thread A: ", "both run inside `main`", "", false],
      ["With Thread C: ", "both use `hal_write`", "", false],
    ]);
  });

  it("has nothing to show for one thread or none", () => {
    expect(sectionConnections([thread("T1")], [conn("T1", "T1")]).size).toBe(0);
    expect(sectionConnections([], [conn("T1", "T2")]).size).toBe(0);
  });
});

describe("the folded rows after the threads (§5.3)", () => {
  const bi = (files: number): BuildImpact => ({ header: "uart.h", text: "", files, finding: null, note: "" });
  const sink: SinkHit = { field: "N7", label: "Stats::tx", users: 9, why: "listed", writers: [] };
  const none = { build_impact: [] as BuildImpact[], coverage: [] as string[], rules_only: false };

  it("leaves out Build impact and Coverage when they have nothing, and keeps Discussion", () => {
    expect(foldTitles(none, [])).toEqual({ build: null, coverage: null, discussion: "Discussion · no comments yet" });
  });

  it("says the most files a change rebuilds", () => {
    expect(foldTitles({ ...none, build_impact: [bi(3), bi(4)] }, []).build).toBe("Build impact · up to 4 files rebuild");
    expect(foldTitles({ ...none, build_impact: [bi(1)] }, []).build).toBe("Build impact · up to 1 file rebuilds");
    expect(foldTitles({ ...none, build_impact: [bi(0)] }, []).build).toBe("Build impact");
  });

  it("counts coverage lines, plus one for rules only and one for shared sinks", () => {
    expect(foldTitles({ ...none, coverage: ["No test code found in the workspace"], rules_only: true }, []).coverage)
      .toBe("Coverage · 2 notes");
    expect(foldTitles({ ...none, coverage: ["No test code found in the workspace"] }, []).coverage).toBe("Coverage · 1 note");
    expect(foldTitles({ ...none, sinks: [sink, sink] }, []).coverage).toBe("Coverage · 1 note");
  });

  it("counts top-level review and layer comments only", () => {
    const c = (parent_id: number | null, anchor_kind: string) => ({ parent_id, anchor_kind });
    expect(foldTitles(none, [c(null, "review"), c(null, "chapter"), c(1, "review"), c(null, "function"), c(null, "story")]).discussion)
      .toBe("Discussion · 2 comments");
    expect(foldTitles(none, [c(null, "review")]).discussion).toBe("Discussion · 1 comment");
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
