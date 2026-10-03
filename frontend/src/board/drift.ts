/** The change panel's workspace-drift lines: warnings (the workspace is behind or lacks the file) apart from the
 * expected case (newer than a submitted change). Drift stored before kinds counts as a warning. */
export interface DriftLine { text: string; kind?: string; severity?: "warn" | "info" }

export function driftSummary(drift: DriftLine[]): { warn: string[]; info: string[] } {
  return { warn: drift.filter((d) => d.severity !== "info").map((d) => d.text),
           info: drift.filter((d) => d.severity === "info").map((d) => d.text) };
}
