import { useEffect, useState } from "react";
import { api, type Health as HealthT } from "../api";

export default function Health() {
  const [h, setH] = useState<HealthT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.health().then(setH).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => { load(); }, []);

  if (error) return <main className="page error">{error}</main>;
  if (!h) return <main className="page muted">Checking…</main>;
  return (
    <main className="page">
      <h1>Health {h.ready ? <span className="badge ok">ready</span> : <span className="badge failed">not ready</span>}</h1>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
        <tbody>
          {h.checks.map((c) => (
            <tr key={c.name}>
              <td>{c.name}{c.hard ? "" : <span className="muted"> (warning only)</span>}</td>
              <td><span className={`badge ${c.ok ? "ok" : c.hard ? "failed" : "degraded"}`}>{c.ok ? "ok" : "fail"}</span></td>
              <td className="mono small">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <section className="card">
        <h2>Symbol index</h2>
        <p>Generation {h.index_generation}{h.index_building ? " — rebuilding…" : ""}</p>
        <button onClick={() => api.rebuildIndex().then(load)}>Rebuild index</button>
      </section>
      <section className="card">
        <h2>Flags stripped for libclang</h2>
        <p className="mono small">{h.strip_flags.length ? h.strip_flags.join(" ") : "none"}</p>
      </section>
      <p className="muted small">Code snippets of changed functions and their callers are sent to the configured LLM endpoint.</p>
    </main>
  );
}
