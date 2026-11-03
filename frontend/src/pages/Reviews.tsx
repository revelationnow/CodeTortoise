import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorText, type ReviewRow, type WorkspaceRow } from "../api";
import { useMe } from "../App";
import { keys, load as loadPref, save as savePref } from "../board/prefs";
import HeadlinePill from "../components/HeadlinePill";
import Logo from "../components/Logo";
import { ago, type Chip, chipCounts, filterReviews, highlight, parseCls, pickOrder, workspaceChips } from "../lib/reviewFilter";
import { CAP } from "../workspace/designContext";

const CHIPS: [Chip, string][] = [["all", "All"], ["high", "High risk"], ["running", "Running"], ["mine", "Mine"]];
const RISK_DOT: Record<string, string> = { high: "#ff4d6d", medium: "#ffb020", low: "#16a34a" };   // same as the risk pills
const LIVE = new Set(["queued", "running"]);

/** Landing page (spec §12): start a review on the left (owner), searchable reviews on the right. With reviews from several
 * workspaces, each row names its workspace and chips filter by workspace (spec 2026-10-31 §9). */
export default function Reviews() {
  const me = useMe();
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [chip, setChip] = useState<Chip>("all");
  const [ws, setWs] = useState<number | null>(null);                     // the workspace chip pressed, if any
  const [owned, setOwned] = useState<WorkspaceRow[] | null>(null);        // New review's workspaces, the last used first
  const owner = !!me?.owner_of.length;                                   // owns a workspace: starts reviews (spec 2026-10-31 §7)

  useEffect(() => {
    let stop = false;
    const load = () => api.reviews().then((r) => { if (!stop) setRows(r); }).catch((e) => setError(errorText(e, "The reviews could not be loaded.")));
    load();
    return () => { stop = true; };
  }, []);
  useEffect(() => {
    if (!owner) return;
    api.workspaces().then((all) => setOwned(pickOrder(all.filter((w) => w.is_owner), loadPref<number | null>(keys.lastWorkspace, null))))
      .catch(() => setOwned([]));                          // the server then takes the only one, or says to choose
  }, [owner]);
  const live = !!rows?.some((r) => LIVE.has(r.status));
  useEffect(() => {                                       // keep running reviews fresh without a reload
    if (!live) return;
    const t = window.setInterval(() => api.reviews().then(setRows).catch(() => {}), 5000);
    return () => window.clearInterval(t);
  }, [live]);

  const who = useMemo(() => Object.fromEntries((me?.logins ?? []).map((l) => [l.server, l.user])), [me]);
  const wsChips = useMemo(() => workspaceChips(rows ?? []), [rows]);
  const wsOn = wsChips.some((c) => c.id === ws) ? ws : null;             // a chip that went away filters nothing
  const shown = useMemo(() => (rows ? filterReviews(rows, query, chip, who, wsOn) : []), [rows, query, chip, who, wsOn]);
  const counts = useMemo(() => chipCounts(rows ?? [], who, wsOn), [rows, who, wsOn]);

  return (
    <main className="home-page">
      <section className="rv-hello">
        {me && owner ? <StartReview owned={owned} only={me.owner_of.length === 1 ? me.owner_of[0] : undefined} /> : (
          <>
            <Logo size={72} />
            <h1>Hi {[...new Set((me?.logins ?? []).map((l) => l.user))].join(", ")}</h1>
            <p>These are the reviews shared on this CodeTortoise. Open one to explore its call flows, side effects and
              changed code, and leave comments where you see something.</p>
          </>
        )}
      </section>
      <section className="rv-main">
        <div className="rv-head">
          <h2>Reviews</h2>
          <label className="rv-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" aria-label="Search reviews" placeholder="Search title, CL, author or status" value={query}
                   onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); }} />
          </label>
        </div>
        <div className="rv-chips">
          {CHIPS.map(([c, label]) => (
            <button key={c} className={chip === c ? "on" : ""} aria-pressed={chip === c} onClick={() => setChip(c)}>
              {label} <span>{counts[c]}</span>
            </button>
          ))}
        </div>
        {wsChips.length > 0 && (
          <div className="rv-chips" role="group" aria-label="Filter by workspace">
            {wsChips.map((c) => (
              <button key={c.id} className={wsOn === c.id ? "on" : ""} aria-pressed={wsOn === c.id} onClick={() => setWs(wsOn === c.id ? null : c.id)}>
                {c.name} <span>{c.count}</span>
              </button>
            ))}
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        {!rows && !error && <p className="muted">Loading…</p>}
        {rows && rows.length === 0 && <p className="muted rv-empty">No reviews yet{owner ? " — start one on the left." : "."}</p>}
        <div className="rv-list">
          {shown.map((r) => (
            <Link key={r.id} to={`/r/${r.id}`} className="rv-row">
              <span className="dot" style={{ background: r.risk ? RISK_DOT[r.risk] : "var(--line)" }} />
              <b>{highlight(r.title, query).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</b>
              {wsChips.length > 0 && r.workspace && <span className="rv-ws">{r.workspace.name}</span>}
              <span className="cls">{r.cls.map((c) => <span key={c} className="cl">{c}</span>)}</span>
              <span className="sp" />
              {r.headline ? <HeadlinePill h={r.headline} className="rv-headline" />
                : r.risk && <span className={`rv-risk ${r.risk}`}>{r.risk.toUpperCase()}</span>}
              <span className={`rv-status ${r.status}`}>{LIVE.has(r.status) ? `${r.status}…` : r.status}</span>
              <span className="when">{ago(r.created_at)} · {r.created_by}</span>
            </Link>
          ))}
        </div>
        {rows && rows.length > 0 && (query || chip !== "all" || wsOn !== null) && (
          <p className="rv-count">{shown.length} of {rows.length} reviews{query ? " · Esc clears" : ""}</p>
        )}
      </section>
    </main>
  );
}

/** New review (spec 2026-10-31 §9): with several workspaces owned, a picker of them (the last used first); `only`: the one
 * workspace owned, while the list loads. */
function StartReview({ owned, only }: { owned: WorkspaceRow[] | null; only?: number }) {
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [context, setContext] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const cls = parseCls(text);
  const chars = [...context.trim()].length;          // what the server counts of it: characters, as sent (trimmed)
  const choices = owned ?? [];
  const target = choices.length > 1 ? picked ?? choices[0].id : choices[0]?.id ?? only;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);                                // a new attempt clears the last refusal, so a repeat is told again
    try {
      const r = await api.createReview(cls, title.trim() || undefined, target, context.trim() || undefined);
      if (target !== undefined) savePref(keys.lastWorkspace, target);
      navigate(`/r/${r.id}`);
    } catch (err) {
      setError(errorText(err, "The review could not be started."));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <Logo size={72} />
      <h1>Review a change</h1>
      <p>Shelved or submitted changelists, one or several; they're stacked in CL order.</p>
      {choices.length > 1 && (
        <>
          <label htmlFor="rv-workspace">Workspace</label>
          <select id="rv-workspace" value={target} onChange={(e) => setPicked(Number(e.target.value))}>
            {choices.map((w) => <option key={w.id} value={w.id}>{w.name}{w.ready ? "" : " (not ready)"}</option>)}
          </select>
        </>
      )}
      <label>Changelists (shelved or submitted)
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="12345 12346" />
      </label>
      <div className="hint">{cls.length ? `Will analyse: ${cls.join(", ")}` : "Enter one or more CL numbers."}</div>
      <label>Title (optional)<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label>Design context (optional)
        <textarea rows={3} value={context} onChange={(e) => setContext(e.target.value)}
                  placeholder="What the change is for, and what the code can't say" />
      </label>
      <div className="hint">The AI's opening reads it; checks never do. More can be added later from the review's ⋯ menu.</div>
      {chars > 0 && <div className={`hint rv-ctx-count${chars > CAP ? " over" : ""}`}>
        {chars.toLocaleString("en-US")} of {CAP.toLocaleString("en-US")} characters</div>}
      {error && <div className="err" role="alert">{error}</div>}
      <button className="go" disabled={!cls.length || busy || chars > CAP}>{busy ? "Starting…" : "Start review"}</button>
      <div className="hint">The board opens on its own when the analysis finishes.</div>
    </form>
  );
}
