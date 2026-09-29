import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ReviewRow } from "../api";
import { RiskBadge, StatusBadge } from "../components/Badges";

export default function Reviews() {
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.reviews().then(setRows).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <main className="page error">{error}</main>;
  if (!rows) return <main className="page muted">Loading…</main>;
  return (
    <main className="page">
      <h1>Reviews</h1>
      {rows.length === 0 ? (
        <p className="muted">No reviews yet.</p>
      ) : (
        <table className="table">
          <thead><tr><th>#</th><th>Title</th><th>CLs</th><th>Status</th><th>Risk</th><th>Created</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td><Link to={`/r/${r.id}`}>{r.title}</Link></td>
                <td className="mono">{r.cls.join(", ")}</td>
                <td><StatusBadge status={r.status} /></td>
                <td><RiskBadge risk={r.risk} /></td>
                <td className="muted">{r.created_at.replace("T", " ").slice(0, 16)} · {r.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
