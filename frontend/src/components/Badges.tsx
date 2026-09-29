export function RiskBadge({ risk }: { risk: string | null }) {
  if (!risk) return <span className="muted">—</span>;
  return <span className={`badge risk-${risk}`}>{risk}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const cls = status === "done" ? "ok" : status;
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge sev-${severity}`}>{severity}</span>;
}
