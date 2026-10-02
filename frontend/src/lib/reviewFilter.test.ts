import { describe, expect, it } from "vitest";
import type { ReviewRow } from "../api";
import { chipCounts, filterReviews, highlight } from "./reviewFilter";

const row = (id: number, title: string, cls: number[], status: string, risk: ReviewRow["risk"], by = "anoop") =>
  ({ id, title, cls, status, risk, created_by: by, created_at: "2026-10-01T10:00:00+00:00" }) as ReviewRow;
const rows = [
  row(1, "Detached HEAD caching", [28, 29], "done", "high"),
  row(2, "planted: output_eol -1", [30], "degraded", "high", "bob"),
  row(3, "upstream 24", [24], "running", "low"),
  row(4, "queued one", [7], "queued", null, "bob"),
];
const ids = (r: ReviewRow[]) => r.map((x) => x.id);

describe("review search", () => {
  it("matches title, CL number, author and status, ignoring case", () => {
    expect(ids(filterReviews(rows, "detach", "all", "anoop"))).toEqual([1]);
    expect(ids(filterReviews(rows, "30", "all", "anoop"))).toEqual([2]);
    expect(ids(filterReviews(rows, "CL 24", "all", "anoop"))).toEqual([3]);
    expect(ids(filterReviews(rows, "BOB", "all", "anoop"))).toEqual([2, 4]);
    expect(ids(filterReviews(rows, "degraded", "all", "anoop"))).toEqual([2]);
    expect(ids(filterReviews(rows, "  ", "all", "anoop"))).toEqual([1, 2, 3, 4]);
    expect(ids(filterReviews(rows, "head caching", "all", "anoop"))).toEqual([1]);   // every word must match
  });

  it("filters by chip and counts each chip", () => {
    expect(ids(filterReviews(rows, "", "high", "anoop"))).toEqual([1, 2]);
    expect(ids(filterReviews(rows, "", "running", "anoop"))).toEqual([3, 4]);       // queued counts as running
    expect(ids(filterReviews(rows, "", "mine", "anoop"))).toEqual([1, 3]);
    expect(ids(filterReviews(rows, "planted", "mine", "anoop"))).toEqual([]);
    expect(chipCounts(rows, "anoop")).toEqual({ all: 4, high: 2, running: 2, mine: 2 });
  });

  it("splits a title into highlighted and plain parts", () => {
    expect(highlight("Detached HEAD caching", "head detach")).toEqual([
      { text: "Detach", hit: true }, { text: "ed ", hit: false }, { text: "HEAD", hit: true }, { text: " caching", hit: false }]);
    expect(highlight("upstream 24", "")).toEqual([{ text: "upstream 24", hit: false }]);
    expect(highlight("a.b(c)", "(c")).toEqual([{ text: "a.b", hit: false }, { text: "(c", hit: true }, { text: ")", hit: false }]);
  });
});
