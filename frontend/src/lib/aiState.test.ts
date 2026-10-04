import { describe, expect, it } from "vitest";
import type { AiJob, AiView } from "../api";
import { aiAvailability, callTitle, finished, jobFor } from "./aiState";

const view = (over: Partial<AiView> = {}): AiView => ({
  used: 57, budget: 200, by_person: {}, by_purpose: {}, llm: true, me_today: 3, me_limit: 100,
  per_mention: 6, is_owner: false, jobs: [], file_summaries: {}, ...over,
});

describe("aiAvailability", () => {
  it("says what @tortoise costs and what is left", () => {
    expect(aiAvailability(view())).toEqual({ ok: true,
      detail: "ask the AI about this thread — reads code as needed, up to 6 AI calls · 143 left on this review, 97 left for you today" });
  });
  it("gives the reason when it can't run", () => {
    expect(aiAvailability(null)).toEqual({ ok: false, detail: "no AI is configured for CodeTortoise" });
    expect(aiAvailability(view({ llm: false }))).toEqual({ ok: false, detail: "no AI is configured for CodeTortoise" });
    expect(aiAvailability(view({ used: 200 })).detail).toBe("this review has used its 200 AI calls; the owner can raise it");
    expect(aiAvailability(view({ me_today: 100 })).detail).toBe("you've used your 100 AI calls today");
  });
});

describe("jobs", () => {
  const j = (id: number, status: AiJob["status"], target = "FL1"): AiJob => ({ id, user: "bob", kind: "flow", target, status, error: null });
  it("finds the latest job for an item", () => {
    expect(jobFor(view({ jobs: [j(1, "failed"), j(2, "running"), j(3, "done", "FL2")] }), "flow", "FL1")?.id).toBe(2);
    expect(jobFor(view(), "flow", "FL1")).toBeUndefined();
  });
  it("lists the jobs that were running, or are new, and have now finished", () => {
    const before = view({ jobs: [j(1, "running"), j(2, "running", "FL2"), j(4, "done", "FL4")] });
    const after = view({ jobs: [j(1, "done"), j(2, "running", "FL2"), j(4, "done", "FL4"), j(3, "done", "FL3")] });
    expect(finished(before, after).map((x) => x.id)).toEqual([1, 3]);     // 3 finished before anyone saw it run
    expect(finished(null, after)).toEqual([]);                            // the first load: nothing new to show
  });
});

describe("callTitle", () => {
  it("names the cost on hover", () => {
    expect(callTitle(view())).toBe("1 AI call · 143 left on this review");
  });
});
