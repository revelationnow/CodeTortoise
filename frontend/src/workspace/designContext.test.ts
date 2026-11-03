import { describe, expect, it } from "vitest";
import { componentsText, contextChars, EMPTY_CONTEXT, noteSentence, parseComponents } from "./designContext";

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

  it("says a note of the design as a sentence", () => {
    expect(noteSentence("the condition `x == 1` is not in the changed functions"))
      .toBe("The condition `x == 1` is not in the changed functions.");
  });
});
