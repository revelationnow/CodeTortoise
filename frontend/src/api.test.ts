import { describe, expect, it } from "vitest";
import { ApiError, errorText } from "./api";

describe("errorText", () => {
  const FALLBACK = "The server did not accept the mark.";

  it("is the words of an error that has some", () => {
    expect(errorText(new ApiError(500, "the store is busy"), FALLBACK)).toBe("the store is busy");
    expect(errorText(new TypeError("Failed to fetch"), FALLBACK)).toBe("Failed to fetch");
    expect(errorText(new Error(" spaced out "), FALLBACK)).toBe("spaced out");
  });

  it("is the fallback for a refusal with no words: no detail and, over HTTP/2, no status text", () => {
    expect(errorText(new ApiError(500, ""), FALLBACK)).toBe(FALLBACK);
    expect(errorText(new Error("   "), FALLBACK)).toBe(FALLBACK);
  });

  it("is a thing thrown that is no error, if it is words, and the fallback otherwise", () => {
    expect(errorText("it broke", FALLBACK)).toBe("it broke");
    expect(errorText({ message: "it broke" }, FALLBACK)).toBe("it broke");
    for (const nothing of ["", "  ", undefined, null, 0, {}, { message: undefined }, { message: 42 }])
      expect(errorText(nothing, FALLBACK), JSON.stringify(nothing)).toBe(FALLBACK);
  });
});
