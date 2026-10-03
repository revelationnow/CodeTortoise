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
      <h1 className="hc-title">Health <span className={`hc-pill ${h.ready ? "ok" : "bad"}`}>● {h.ready ? "ready" : "not ready"}</span></h1>
      <div className="hc-list">
        {h.checks.map((c) => {
          const kind = c.ok ? "ok" : c.hard ? "bad" : "warn";
          return (
            <div key={c.name} className={`hc-row ${kind}`}>
              <span className="icon">{c.ok ? "✓" : c.hard ? "✗" : "!"}</span>
              <div><b>{c.name}</b>{!c.hard && <span className="muted small"> · warning only</span>}<div className="detail">{c.detail}</div></div>
            </div>
          );
        })}
      </div>
      <div className="hc-cards">
        <section className="card">
          <h2>Symbol index</h2>
          <p>Generation {h.index_generation}{h.index_building ? " — rebuilding…" : ""}</p>
          <button onClick={() => api.rebuildIndex().then(load)}>Rebuild index</button>
        </section>
        <section className="card">
          <h2>Flags stripped for libclang</h2>
          <p className="mono small">{h.strip_flags.length ? h.strip_flags.join(" ") : "none"}</p>
        </section>
        {h.ai?.limits && (
          <section className="card">
            <h2>AI calls</h2>
            <p className="small">Limits: {h.ai.limits.per_review} a review · {h.ai.limits.per_person_daily} a person a day ·{" "}
              {h.ai.limits.per_mention} for one @tortoise answer</p>
            <p className="small">Today: {h.ai.calls_today ?? 0} calls across reviews</p>
          </section>
        )}
        {Object.keys(h.p4_sources ?? {}).length > 0 && (
          <section className="card">
            <h2>Perforce settings from</h2>
            {Object.entries(h.p4_sources).map(([k, v]) => <p key={k} className="small"><b>{k}</b> · {v}</p>)}
          </section>
        )}
      </div>
      <p className="muted small">Code snippets of changed functions and their callers are sent to the configured LLM endpoint.</p>
    </main>
  );
}
