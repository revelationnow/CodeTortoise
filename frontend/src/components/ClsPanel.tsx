import { useState } from "react";
import { api, type ClRow } from "../api";
import { useMe } from "../App";

export default function ClsPanel({ reviewId, cls, onChange }: { reviewId: number; cls: ClRow[]; onChange: () => void }) {
  const me = useMe();
  const [msg, setMsg] = useState<string | null>(null);
  const run = (p: Promise<unknown>, ok: string) => p.then(() => { setMsg(ok); onChange(); }).catch((e) => setMsg(String(e.message ?? e)));
  return (
    <div className="cls">
      {msg && <div className="banner">{msg}</div>}
      <div className="table-wrap"><table className="table">
        <thead><tr><th>CL</th><th className="opt">Status</th><th className="opt">Author</th><th>Description</th><th>Swarm</th>{me?.is_owner && <th />}</tr></thead>
        <tbody>
          {cls.map((c) => (
            <tr key={c.cl}>
              <td className="mono">{c.cl}</td>
              <td className="opt">{c.status}</td>
              <td className="opt">{c.user}</td>
              <td className="small">{c.description}</td>
              <td>{c.swarm ? (
                <a href={c.swarm.url} target="_blank" rel="noreferrer">#{c.swarm.id} {c.swarm.state_label ?? c.swarm.state}</a>
              ) : <span className="muted">none</span>}
                {c.swarm && Object.keys(c.swarm.votes).length > 0 && (
                  <div className="small muted">{Object.entries(c.swarm.votes).map(([u, v]) => `${u} ${v > 0 ? "+" : ""}${v}`).join(", ")}</div>
                )}
              </td>
              {me?.is_owner && (
                <td className="actions">
                  <button className="link small" onClick={() => run(api.swarmRefresh(reviewId, c.cl), "Swarm state refreshed")}>refresh</button>
                  {!c.swarm && c.status === "pending" && (
                    <button className="link small" onClick={() => run(api.swarmCreate(reviewId, c.cl), "Swarm review created")}>create review</button>
                  )}
                  {c.swarm && (
                    <button className="link small" onClick={() => run(
                      api.swarmPost(reviewId, c.cl).catch((e) => {
                        if (e.status === 409 && confirm("A summary was already posted. Post again?")) return api.swarmPost(reviewId, c.cl, true);
                        throw e;
                      }), "Summary link posted to Swarm")}>post summary link</button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table></div>
    </div>
  );
}
