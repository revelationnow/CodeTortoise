/** The rail's derived data (spec 2026-10-04-review-workspace §2.2): the stories shown as drawn from the change set. */
import type { Finding, Severity } from "../api";
import type { StorySet } from "../board/types";

/** The CLs the stories draw from, for "Stories (from N CLs)". */
export function storyCls(ss: StorySet): number[] {
  return [...new Set(ss.stories.flatMap((s) => s.cls))].sort((a, b) => a - b);
}

/** The stories a CL filter lights (the rest are dimmed); null when no filter is set. */
export function litStories(ss: StorySet, cl: number | null): Set<string> | null {
  return cl === null ? null : new Set(ss.stories.filter((s) => s.cls.includes(cl)).map((s) => s.id));
}

export const SEVERITIES: Severity[] = ["high", "medium", "low", "info"];

export function bySeverity(findings: Finding[]): { severity: Severity; findings: Finding[] }[] {
  return SEVERITIES.map((severity) => ({ severity, findings: findings.filter((f) => f.severity === severity) }))
    .filter((g) => g.findings.length);
}
