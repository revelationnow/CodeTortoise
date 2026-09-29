import { useMemo, useState } from "react";
import type { Impact } from "../api";
import { blastRings } from "../lib/graph";

interface Props { impact: Impact; onCite: (id: string) => void; layerName: (level: number | null) => string }

export default function BlastRadius({ impact, onCite, layerName }: Props) {
  const [via, setVia] = useState<"all" | "call" | "data">("all");
  const [layer, setLayer] = useState<string>("all");
  const [conf, setConf] = useState<"all" | "precise">("all");
  const layers = [...new Set(impact.blast.map((b) => impact.nodes[b.node].layer))];
  const filtered = useMemo(() => ({
    ...impact,
    blast: impact.blast.filter((b) => {
      const n = impact.nodes[b.node];
      return (via === "all" || b.via === via) && (layer === "all" || String(n.layer) === layer)
        && (conf === "all" || n.confidence === "precise");
    }),
  }), [impact, via, layer, conf]);
  const rings = blastRings(filtered);
  const max = Math.max(1, ...impact.blast.map((b) => b.score));

  return (
    <div className="blast">
      <div className="toolbar">
        <label>Via <select value={via} onChange={(e) => setVia(e.target.value as typeof via)}>
          <option value="all">call + data</option><option value="call">call</option><option value="data">field data</option>
        </select></label>
        <label>Layer <select value={layer} onChange={(e) => setLayer(e.target.value)}>
          <option value="all">all</option>
          {layers.map((l) => <option key={String(l)} value={String(l)}>{layerName(l)}</option>)}
        </select></label>
        <label>Confidence <select value={conf} onChange={(e) => setConf(e.target.value as typeof conf)}>
          <option value="all">all</option><option value="precise">precise nodes only</option>
        </select></label>
      </div>
      <p className="small muted">
        Seeds: {impact.changed.map((id) => impact.nodes[id].label).join(", ")}. Score = Σ(edge confidence / hop),
        boosted for cross-layer callers, entry points and virtual dispatch.
      </p>
      {[...rings.keys()].sort((a, b) => a - b).map((hop) => (
        <section key={hop} className="card ring">
          <h3>Hop {hop}</h3>
          <table className="table">
            <tbody>
              {rings.get(hop)!.map((r) => {
                const n = impact.nodes[r.id];
                const item = impact.blast.find((b) => b.node === r.id)!;
                return (
                  <tr key={r.id}>
                    <td style={{ width: "30%" }}><button className="link" onClick={() => onCite(r.id)}>{n.label}</button></td>
                    <td style={{ width: 140 }}><div className="bar"><div style={{ width: `${(100 * r.score) / max}%` }} /></div></td>
                    <td className="mono small">{r.score}</td>
                    <td><span className={`badge via-${r.via}`}>{r.via}</span></td>
                    <td className="small muted">{layerName(n.layer)} · {n.confidence}</td>
                    <td className="small muted">{item.path.map((p) => impact.nodes[p].label).join(" → ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
      {impact.fanout.length > 0 && (
        <section className="card">
          <h3>Header fan-out</h3>
          <table className="table">
            <thead><tr><th>Header</th><th>TUs</th><th>By layer</th></tr></thead>
            <tbody>{impact.fanout.map((f) => (
              <tr key={f.header}>
                <td className="mono small">{f.header}</td><td>{f.total_tus}</td>
                <td className="small">{Object.entries(f.by_layer).map(([k, v]) => `${k}: ${v}`).join(" · ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      )}
    </div>
  );
}
