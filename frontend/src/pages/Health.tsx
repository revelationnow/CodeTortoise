import { useEffect, useState } from "react";
import { api, type Health as HealthT, type SinkRules } from "../api";
import SinkMark from "../components/SinkMark";

export default function Health() {
  const [h, setH] = useState<HealthT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sinks, setSinks] = useState<SinkRules | null>(null);
  const load = () => {
    api.sinks().then(setSinks).catch(() => setSinks(null));
    return api.health().then(setH).catch((e) => setError(String(e.message ?? e)));
  };
  useEffect(() => { load(); }, []);

  if (error) return <main className="page error">{error}</main>;
  if (!h) return <main className="page muted">Checking…</main>;
  return (
    <main className="page">
      <h1 className="hc-title">Health <span className={`hc-pill ${h.ready ? "ok" : "bad"}`}>● {h.ready ? "ready" : "not ready"}</span></h1>
      {h.checks.flatMap((c) => /code from reviewed changes is sent to (\S+)/.exec(c.detail)?.[1] ?? []).map((host) => (
        <div key={host} className="banner warn" role="note">Code from reviewed changes is sent to <b>{host}</b>, the strong
          model's endpoint. Point <code>llm.strong.base_url</code> at a model on your network to keep it in house.</div>
      ))}
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
              {h.ai.limits.per_mention} rounds for one @tortoise answer (1 call; owners can change it per review)</p>
            <p className="small">Today: {h.ai.calls_today ?? 0} calls across reviews</p>
          </section>
        )}
        {sinks && (
          <section className="card">
            <h2>Shared sinks</h2>
            <p>{sinks.threshold > 0 ? `A field more than ${sinks.threshold} unchanged functions touch` : "No threshold (sink_threshold: 0)"}</p>
            <p className="mono small">In tortoise.yaml: {sinks.patterns.length ? sinks.patterns.join(" ") : "none"}</p>
            <p>Marked: {sinks.marked.length ? sinks.marked.map((m) => <span key={m}><code>{m}</code> <SinkMark label={m} on /> </span>) : "none"}</p>
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
