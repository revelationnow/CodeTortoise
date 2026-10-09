import type { AiCall } from "../api";

/** The zip of a review's logged AI requests, or of one call's (spec 2026-10-08-llm-robustness §8.2). */
export function requestLogHref(reviewId: number, call?: number): string {
  return `/api/reviews/${reviewId}/ai/requests.zip` + (call === undefined ? "" : `?call=${call}`);
}

export function hasRequests(calls: AiCall[] | null): boolean {
  return (calls ?? []).some((c) => c.requests > 0);
}
