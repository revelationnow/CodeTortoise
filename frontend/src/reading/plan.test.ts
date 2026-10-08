import { describe, expect, it } from "vitest";
import { nextUnread, progress, progressText, threadRead } from "./plan";
import type { Check, Reading } from "./types";

const check = (key: string) => ({ key }) as Check;
const reading = { order: ["S2", "S1", "S3", "S4"], checks: [check("a"), check("b"), check("c")],
                  cleared: [check("z")] } as unknown as Reading;

describe("the reading plan (spec 2026-10-07-review-reading-phase2 §6)", () => {
  it("goes to the next story in reading order the reader has not read, wrapping, and nowhere when all are read", () => {
    expect(nextUnread(reading.order, new Set(["S2"]), "S2")).toBe("S1");
    expect(nextUnread(reading.order, new Set(["S2", "S1", "S4"]), "S4")).toBe("S3");
    expect(nextUnread(reading.order, new Set(["S2", "S1", "S3", "S4"]), "S1")).toBeNull();
  });

  it("counts read stories and checks, ignoring ticks the reading no longer holds", () => {
    const p = progress(reading, { stories: ["S1", "S9"], checks: ["a", "z", "gone"] });
    expect(p).toEqual({ stories: 1, storyCount: 4, checks: 1, checkCount: 3, all: false });
    expect(progressText(p)).toBe("1 of 4 stories read · 1 of 3 checks");
    expect(progressText(progress({ ...reading, checks: [] }, { stories: [], checks: [] }))).toBe("0 of 4 stories read");
    expect(progress(reading, { stories: ["S1", "S2", "S3", "S4"], checks: [] }).all).toBe(true);
  });

  it("says how much of a thread the reader has read", () => {
    expect(threadRead(["S2", "S1", "S3"], new Set(["S1", "S3"]))).toBe("2 of 3");
  });
});
