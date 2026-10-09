import { describe, expect, it } from "vitest";
import type { AiCall } from "../api";
import { hasRequests, requestLogHref } from "./requestLog";

const call = (id: number, requests: number): AiCall => ({
  id, user: "pipeline", purpose: "stories", target: "chunk 1", model: "big", started_at: "2026-10-08T10:00:00+00:00",
  finished_at: null, prompt_tokens: null, completion_tokens: null, outcome: "ok", error: null, requests,
});

describe("request log links (spec 2026-10-08-llm-robustness §8.2)", () => {
  it("links the whole review's log, or one call's", () => {
    expect(requestLogHref(7)).toBe("/api/reviews/7/ai/requests.zip");
    expect(requestLogHref(7, 12)).toBe("/api/reviews/7/ai/requests.zip?call=12");
  });

  it("offers the download only when a call holds requests", () => {
    expect(hasRequests(null)).toBe(false);
    expect(hasRequests([call(1, 0)])).toBe(false);
    expect(hasRequests([call(1, 0), call(2, 3)])).toBe(true);
  });
});
