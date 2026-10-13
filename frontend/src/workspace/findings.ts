/** Index › Findings' rules (spec 2026-10-12-story-account-and-panels §4): the worst first, then by id; filtered by
 * severity and status. */
import type { Finding, Severity } from "../api";

export const SEVERITIES: Severity[] = ["high", "medium", "low", "info"];
export type FindingState = Finding["state"];
export const FINDING_STATES: FindingState[] = ["open", "ack", "dismissed"];
export const STATE_LABEL: Record<FindingState, string> = { open: "open", ack: "acknowledged", dismissed: "dismissed" };

const num = (id: string) => Number(id.replace(/\D/g, "")) || 0;

export function listFindings(fs: Finding[], sev: Severity | null, status: FindingState | null): Finding[] {
  return fs.filter((f) => (!sev || f.severity === sev) && (!status || f.state === status))
    .sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity) || num(a.id) - num(b.id)
      || a.id.localeCompare(b.id));
}
