import { describe, expect, it } from "vitest";
import type { ReviewRow } from "../api";
import { chipCounts, filterReviews, highlight } from "./reviewFilter";

const LOCAL = { id: 1, name: "fw", server: "local" }, SECOND = { id: 2, name: "dsp", server: "second:1666" };
const row = (id: number, title: string, cls: number[], status: string, risk: ReviewRow["risk"], by = "amy", workspace = LOCAL) =>
  ({ id, title, cls, status, risk, created_by: by, created_at: "2026-10-01T10:00:00+00:00", workspace }) as ReviewRow;
const rows = [
  row(1, "Detached HEAD caching", [28, 29], "done", "high"),
  row(2, "planted: output_eol -1", [30], "degraded", "high", "bob"),
  row(3, "upstream 24", [24], "running", "low"),
  row(4, "queued one", [7], "queued", null, "bob"),
];
const ids = (r: ReviewRow[]) => r.map((x) => x.id);
const AMY = { local: "amy" };                               // the session: amy, signed in to local only

describe("review search", () => {
  it("matches title, CL number, author and status, ignoring case", () => {
    expect(ids(filterReviews(rows, "detach", "all", AMY))).toEqual([1]);
    expect(ids(filterReviews(rows, "30", "all", AMY))).toEqual([2]);
    expect(ids(filterReviews(rows, "CL 24", "all", AMY))).toEqual([3]);
    expect(ids(filterReviews(rows, "BOB", "all", AMY))).toEqual([2, 4]);
    expect(ids(filterReviews(rows, "degraded", "all", AMY))).toEqual([2]);
    expect(ids(filterReviews(rows, "  ", "all", AMY))).toEqual([1, 2, 3, 4]);
    expect(ids(filterReviews(rows, "head caching", "all", AMY))).toEqual([1]);   // every word must match
  });

  it("filters by chip and counts each chip", () => {
    expect(ids(filterReviews(rows, "", "high", AMY))).toEqual([1, 2]);
    expect(ids(filterReviews(rows, "", "running", AMY))).toEqual([3, 4]);       // queued counts as running
    expect(ids(filterReviews(rows, "", "mine", AMY))).toEqual([1, 3]);
    expect(ids(filterReviews(rows, "planted", "mine", AMY))).toEqual([]);
    expect(chipCounts(rows, AMY)).toEqual({ all: 4, high: 2, running: 2, mine: 2 });
  });

  it("counts as Mine a review made by the session's sign-in on that review's own server", () => {
    const two = [...rows, row(5, "same name elsewhere", [9], "done", null, "amy", SECOND), row(6, "theirs", [10], "done", null, "bob", SECOND)];
    expect(ids(filterReviews(two, "", "mine", AMY))).toEqual([1, 3]);              // amy on local is not the amy of second:1666
    expect(ids(filterReviews(two, "", "mine", { local: "amy", "second:1666": "bob" }))).toEqual([1, 3, 6]);
    expect(chipCounts(two, {}).mine).toBe(0);
  });

  it("splits a title into highlighted and plain parts", () => {
    expect(highlight("Detached HEAD caching", "head detach")).toEqual([
      { text: "Detach", hit: true }, { text: "ed ", hit: false }, { text: "HEAD", hit: true }, { text: " caching", hit: false }]);
    expect(highlight("upstream 24", "")).toEqual([{ text: "upstream 24", hit: false }]);
    expect(highlight("a.b(c)", "(c")).toEqual([{ text: "a.b", hit: false }, { text: "(c", hit: true }, { text: ")", hit: false }]);
  });
});
