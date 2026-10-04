import { type ReactNode, useState } from "react";
import type { Comment } from "../api";
import "./board.css";
import ChangePanel from "./ChangePanel";
import { bandsOf, clusterOfFile, linkedTo, linkLines, nearestCluster } from "./overview";
import { keys, loadAboutOpen, loadWidth, save } from "./prefs";
import type { Action } from "./reducer";
import type { Overview } from "./types";

interface Props {
  reviewId: number;
  ov: Overview;
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  head: (extra: ReactNode) => ReactNode;
  /** Open a cluster's board, optionally with a file open in its viewer. */
  onOpen: (cluster: string, file?: string) => void;
}

/** A split review's overview (spec 2026-10-03-large-change-boards §5): the clusters in the layer bands, with their risk,
 * counts and links; the whole change's summary beside them. */
export default function OverviewPage({ reviewId, ov, comments, onComments, risk, head, onOpen }: Props) {
  const [sel, setSel] = useState<string | null>(null);
  const [about, setAbout] = useState(() => loadAboutOpen() ?? window.innerWidth > 1100);
  const [aboutW, setAboutW] = useState(() => loadWidth(keys.aboutW, 360));
  const lit = sel ? linkedTo(ov, sel) : new Set<string>();
  const t = ov.totals;
  const dispatch = (a: Action) => {                       // the panel's file tree opens the file's (or nearest) cluster board
    if (a.t !== "viewer.open") return;
    const c = nearestCluster(ov, a.path);
    if (c) onOpen(c, a.path);
  };
  return (
    <div className="bd ov-page">
      {head(<span className="bd-pill ghost">{t.files} files · {t.clusters} clusters · {t.flows} flows · {t.findings} findings</span>)}
      <div className={`bd-main${about ? " with-about" : ""}`}>
        <ChangePanel open={about} onToggle={() => { save(keys.about, !about); setAbout(!about); }} reviewId={reviewId}
                     comments={comments} onComments={onComments} layers={ov.layers} about={ov.about} sideEffects={[]} risk={risk}
                     openFiles={[]} dispatch={dispatch} wide={window.innerWidth > 1100} width={aboutW} onWidth={setAboutW}
                     fileTag={(p) => { const c = clusterOfFile(ov, p); return c ? ov.clusters.find((x) => x.id === c)?.name ?? c : null; }}
                     onWidthDone={(w) => save(keys.aboutW, w)} />
        <div className="ov-bands" aria-label="Clusters">
          <p className="ov-lead">This change is split into {t.clusters} parts of connected code, riskiest first. Select one to see what
            it's linked to; open it for its board.{ov.merged_over_limit > 0 && ` ${ov.merged_over_limit} small parts were merged to keep the list short.`}</p>
          {bandsOf(ov).map((b) => (
            <section key={b.level} className={`ov-band lv${b.level < 0 ? "x" : b.level % 4}`} aria-label={`Layer ${b.name}`}>
              <h3>{b.name}</h3>
              <div className="ov-blocks">
                {b.clusters.map((c) => (
                  <div key={c.id} role="button" tabIndex={0} aria-pressed={sel === c.id} data-cluster={c.id}
                       className={`ov-block ${c.risk ?? "none"}${sel === c.id ? " sel" : ""}${lit.has(c.id) ? " lit" : ""}`}
                       onClick={() => setSel(sel === c.id ? null : c.id)} onDoubleClick={() => onOpen(c.id)}
                       onKeyDown={(e) => { if (e.key === "Enter") onOpen(c.id); }}>
                    <button className="ov-open" onClick={(e) => { e.stopPropagation(); onOpen(c.id); }}
                            aria-label={`Open ${c.name}`}>Open ›</button>
                    <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
                    <div className="ct"><span className="files-count">{c.files.length} files · </span>{c.changed} changed · {c.flows} flows
                      {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
                    {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
                    {c.also.length > 0 && (
                      <div className="also">also in {c.also.map((lv) => ov.layers.find((l) => l.level === lv)?.name ?? `L${lv}`).join(", ")}</div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
