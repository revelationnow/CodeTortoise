import { describe, expect, it } from "vitest";
import { aiTitle, storyModel } from "./aiMarks";

describe("the hover on AI-written text", () => {
  it("says the AI wrote it, naming the model only when the app knows it", () => {
    expect(aiTitle()).toBe("Written by AI");
    expect(aiTitle(null)).toBe("Written by AI");
    expect(aiTitle("fake-strong")).toBe("Written by AI · fake-strong");
  });
  it("names the strong model for a story's own text only when the strong model formed the story", () => {
    expect(storyModel({ source: "tier1" }, { strong: "fake-strong" })).toBe("fake-strong");
    expect(storyModel({ source: "tier1" }, { strong: null })).toBeNull();
    expect(storyModel({ source: "rules" }, { strong: "fake-strong" })).toBeNull();
    expect(storyModel({}, null)).toBeNull();
  });
});
