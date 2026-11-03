import { describe, expect, it } from "vitest";
import { componentsText, contextChars, docName, EMPTY_CONTEXT, firstLines, linkName, noteSentence, parseComponents,
  sameContext } from "./designContext";

describe("the design context panel's text (spec 2026-11-02 §8)", () => {
  it("holds the components a line each, a name then its globs", () => {
    const cs = [{ name: "Driver", globs: ["driver/**"] }, { name: "HAL", globs: ["hal/**", "include/hal/**"] }];
    expect(componentsText(cs)).toBe("Driver: driver/**\nHAL: hal/**, include/hal/**");
    expect(parseComponents("Driver: driver/**\n\n HAL :hal/**,  include/hal/** \n")).toEqual({ components: cs, bad: [] });
    expect(parseComponents("Driver\n: x/**\nApp: ")).toEqual({ components: [], bad: ["Driver", ": x/**", "App:"] });
  });

  it("counts the characters the prompts read, as the server does", () => {
    expect(contextChars(EMPTY_CONTEXT)).toBe(0);
    const c = { ...EMPTY_CONTEXT, notes: " Never drop a byte. ", documents: [{ name: "d", text: "y😀", url: null }, { name: "e", text: " ", url: null }] };
    expect(contextChars(c)).toBe("Never drop a byte.".length + 2 + "DOCUMENT d:\n".length + 2);   // the emoji is one character
  });

  it("names a link's document by its last path segment, read, and at most 200 characters (final review I4)", () => {
    expect(linkName(" https://wiki.example.com/display/HW/UART%20Driver%20Design ")).toBe("UART Driver Design");
    expect(linkName("https://wiki.example.com/pages/viewpage.action?pageId=123456")).toBe("viewpage.action?pageId=123456");
    expect(linkName("https://wiki.example.com/design/")).toBe("design");
    expect(linkName("https://wiki.example.com")).toBe("wiki.example.com");
    expect(linkName("https://wiki.example.com/x/100%25%E0%A4%A")).toBe("100%25%E0%A4%A");      // not an escape: as written
    expect([...linkName(`https://wiki.example.com/${"😀".repeat(300)}`)]).toHaveLength(200);
    expect(linkName("not a link")).toBe("not a link");
  });

  it("cuts a file's name to the 200 characters a document's name holds", () => {
    expect(docName(" notes.md ")).toBe("notes.md");
    expect(docName(`${"é".repeat(250)}.md`)).toBe("é".repeat(200));
  });

  it("tells a draft from the saved context whatever order its keys come in (final review I5)", () => {
    const saved = { notes: "n", documents: [{ name: "d", text: "t", url: null }],
                    conditions: { add: [{ test: "x", function: null }], remove: [] }, components: [{ name: "A", globs: ["a/**"] }] };
    const draft = { components: [{ globs: ["a/**"], name: "A" }], conditions: { remove: [], add: [{ function: null, test: "x" }] },
                    documents: [{ url: null, text: "t", name: "d" }], notes: "n" };
    expect(sameContext(draft, saved)).toBe(true);
    expect(sameContext({ ...draft, notes: "m" }, saved)).toBe(false);
    expect(sameContext({ ...draft, documents: [] }, saved)).toBe(false);
  });

  it("shows a document's first lines that hold text, each at most 200 characters (phase 3 minor 8)", () => {
    expect(firstLines("# UART\n\n  Never drop a byte.  \n\nA\nB\nC\nD\nE")).toBe("# UART\n  Never drop a byte.\nA\nB\nC");
    expect(firstLines(`${"é".repeat(250)}\nx`, 1)).toBe(`${"é".repeat(200)}…`);
    expect(firstLines("  \n ")).toBe("");
  });

  it("says a note of the design as a sentence", () => {
    expect(noteSentence("the condition `x == 1` is not in the changed functions"))
      .toBe("The condition `x == 1` is not in the changed functions.");
  });
});
