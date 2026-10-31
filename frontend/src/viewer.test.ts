import { describe, expect, it } from "vitest";
import type { ReviewDetail } from "./api";
import { viewerOf } from "./viewer";

const detail = (viewer: ReviewDetail["viewer"]) =>
  ({ review: {}, cls: [], stages: [], workspace: { id: 2, name: "dsp", server: "second:1666" }, viewer }) as unknown as ReviewDetail;

describe("who the session is inside a review (spec 2026-10-31 §8)", () => {
  it("is the review's own viewer: the sign-in on its server, and whether that sign-in owns its workspace", () => {
    expect(viewerOf(detail({ user: "mallory", is_owner: false }))).toEqual(
      { user: "mallory", is_owner: false, workspace: { id: 2, name: "dsp", server: "second:1666" } });
    expect(viewerOf(detail({ user: "owner", is_owner: true }))?.is_owner).toBe(true);
  });

  it("is nobody until the review has loaded", () => {
    expect(viewerOf(null)).toBeNull();
  });
});
