import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import "../board/board.css";
import { driftSummary } from "../board/drift";
import AiPill from "../components/AiPill";
import Stages from "../components/Stages";
import { AiProvider } from "../lib/ai";
import { type Address, at, href, type Open, type Place, readAddress, type Tab } from "./address";
import { useWs as useWs, type Ws, WsContext } from "./context";
import Crumbs, { PhoneBar } from "./Crumbs";
import { type Crumb, crumbs } from "./crumbs";
import { useScreen } from "./media";
import { loadMemory, recall, remember, saveMemory } from "./memory";
import Rail from "./Rail";
import { useReview } from "./useReview";
import WholePage from "./WholePage";
import "./workspace.css";

/** Where the workspace lives (spec 2026-10-04-review-workspace §6: `/w/` while it is built, then `/r/`). */
export const base = (id: number) => `/w/${id}`;

/** The review workspace (spec 2026-10-04-review-workspace §2): header, rail, centre and the detail panel on demand. */
export default function Workspace() {
  const params = useParams();
  const id = Number(params.id);
  const [q] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const data = useReview(id);
  const screen = useScreen();
  const [drawer, setDrawer] = useState(false);
  const root = base(id);
  const addr = useMemo(() => readAddress(`/${params["*"] ?? ""}`, q), [params, q]);
  const [memory, setMemory] = useState(() => loadMemory(id));
  useEffect(() => setMemory((m) => { const n = remember(m, addr); saveMemory(id, n); return n; }), [id, addr]);

  const link = useCallback((a: Address) => href(root, a), [root]);
  const go = useCallback((a: Address, replace = false) => navigate(href(root, a), { replace }), [navigate, root]);
  const item = useCallback((p: Place) => recall(memory, p), [memory]);
  const opened = useCallback((open: Open, tab: Tab = "diff") => ({ ...addr, open, tab }), [addr]);
  const ws: Ws = useMemo(() => ({ base: root, data, addr, screen, link, go, item, opened }),
                         [root, data, addr, screen, link, go, item, opened]);

  const d = data.detail;
  const trail = useMemo(() => crumbs(addr.place, {
    base: root, title: d?.review.title ?? `Review ${id}`, stories: data.stories?.stories ?? [], findings: data.findings,
    cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [],
  }), [addr.place, root, d, id, data.stories, data.findings, data.overview]);
  const hash = location.hash.slice(1) || null;
  const level = addr.open ? "detail" : addr.place.kind === "whole" && !(location.state as { page?: boolean } | null)?.page ? "rail" : "item";

  if (data.error) return <main className="page error">{data.error}</main>;
  if (!d) return <main className="page muted">Loading…</main>;
  return (
    <AiProvider value={data.ai}>
      <WsContext.Provider value={ws}>
        <main className={`ws ${screen} level-${level}${drawer ? " drawer" : ""}`}>
          <Head onMenu={() => setDrawer(!drawer)} drawer={drawer} />
          <div className={`ws-body${addr.open ? " with-detail" : ""}`}>
            {(screen !== "phone" || level === "rail") && <Rail show={hash} onPick={() => setDrawer(false)} />}
            {drawer && <div className="ws-scrim" onClick={() => setDrawer(false)} aria-hidden />}
            {(screen !== "phone" || level === "item") && (
              <section className="ws-centre" aria-label="Centre">
                {screen === "phone" ? <PhoneBar {...phoneBar(trail)} /> : <Crumbs items={trail} />}
                <Centre />
              </section>
            )}
          </div>
        </main>
      </WsContext.Provider>
    </AiProvider>
  );
}

/** "‹ Stories · S1 frame_pop writes…": back to the section, then the item. */
function phoneBar(trail: Crumb[]): { back: Crumb; title: string; handle?: string } {
  if (trail.length === 1) return { back: { label: "Contents", to: trail[0].to ?? "." }, title: "Whole change" };
  const [home, section, me] = trail;
  return me ? { back: section, title: me.label, handle: me.handle } : { back: home, title: section.label };
}

function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
  const ws = useWs(), me = useMe(), d = ws.data, r = d.detail!.review;
  const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
  const drift = driftSummary(d.about?.drift ?? []).warn;
  return (
    <header className="ws-head">
      <button className="ws-menu" aria-label="Review contents" aria-expanded={drawer} title="Show the review's contents"
              onClick={onMenu}>☰</button>
      <h1><Link to={ws.base} state={{ page: true }} title="Go to the whole change">{r.title}</Link></h1>
      {r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
      {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
      {d.ready && <AiPill />}
      {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
      {drift.length > 0 && <span className="bd-pill high" title={drift.join("\n")}>⚠ workspace drift ({drift.length})</span>}
      {notes.length > 0 && (
        <details className="bd-notes">
          <summary>{notes.length} stage note(s)</summary>
          {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
        </details>
      )}
    </header>
  );
}

/** What the address names, or what is missing (spec §7). */
function Centre() {
  const ws = useWs(), d = ws.data, p = ws.addr.place;
  if (!d.ready) return <div className="ws-page"><Stages stages={d.detail!.stages} /><p className="muted">Analysis in progress…</p></div>;
  const exists = p.kind === "whole" || (p.kind === "story" && !!d.stories?.stories.some((s) => s.id === p.sid))
    || (p.kind === "finding" && d.findings.some((f) => f.id === p.fid)) || (p.kind === "cl" && !!d.detail?.cls.some((c) => c.cl === p.cl))
    || (p.kind === "cluster" && !!d.overview?.clusters.some((c) => c.id === p.cid));
  if (!exists) return <Missing what={p} />;
  if (p.kind === "whole") return <WholePage />;
  return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
}

export function Missing({ what }: { what: Place }) {
  const ws = useWs();
  const name = what.kind === "story" ? `Story ${what.sid}` : what.kind === "finding" ? `Finding ${what.fid}`
    : what.kind === "cl" ? `CL ${what.cl}` : what.kind === "cluster" ? `Part ${what.cid}` : "This page";
  return (
    <div className="ws-page">
      <div className="banner warn">{name} isn't in this review. <Link to={ws.link(at({ kind: "whole" }))} state={{ page: true }}>Whole change</Link></div>
    </div>
  );
}
