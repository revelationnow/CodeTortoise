import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type ReviewRow } from "../api";
import { useMe } from "../App";
import HeadlinePill from "../components/HeadlinePill";
import Logo from "../components/Logo";
import { ago, type Chip, chipCounts, filterReviews, highlight, parseCls } from "../lib/reviewFilter";

const CHIPS: [Chip, string][] = [["all", "All"], ["high", "High risk"], ["running", "Running"], ["mine", "Mine"]];
const RISK_DOT: Record<string, string> = { high: "#ff4d6d", medium: "#ffb020", low: "#16a34a" };   // same as the risk pills
const LIVE = new Set(["queued", "running"]);

/** Landing page (spec §12): start a review on the left (owner), searchable reviews on the right. */
export default function Reviews() {
  const me = useMe();
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [chip, setChip] = useState<Chip>("all");

  useEffect(() => {
    let stop = false;
    const load = () => api.reviews().then((r) => { if (!stop) setRows(r); }).catch((e) => setError(String(e.message ?? e)));
    load();
    return () => { stop = true; };
  }, []);
  const live = !!rows?.some((r) => LIVE.has(r.status));
  useEffect(() => {                                       // keep running reviews fresh without a reload
    if (!live) return;
    const t = window.setInterval(() => api.reviews().then(setRows).catch(() => {}), 5000);
    return () => window.clearInterval(t);
  }, [live]);

  const shown = useMemo(() => (rows ? filterReviews(rows, query, chip, me?.user ?? null) : []), [rows, query, chip, me]);
  const counts = useMemo(() => chipCounts(rows ?? [], me?.user ?? null), [rows, me]);

  return (
    <main className="home-page">
      <section className="rv-hello">
        {me?.is_owner ? <StartReview /> : (
          <>
            <Logo size={72} />
            <h1>Hi {me?.user}</h1>
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
        {error && <p className="error">{error}</p>}
        {!rows && !error && <p className="muted">Loading…</p>}
        {rows && rows.length === 0 && <p className="muted rv-empty">No reviews yet{me?.is_owner ? " — start one on the left." : "."}</p>}
        <div className="rv-list">
          {shown.map((r) => (
            <Link key={r.id} to={`/r/${r.id}`} className="rv-row">
              <span className="dot" style={{ background: r.risk ? RISK_DOT[r.risk] : "var(--line)" }} />
              <b>{highlight(r.title, query).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</b>
              <span className="cls">{r.cls.map((c) => <span key={c} className="cl">{c}</span>)}</span>
              <span className="sp" />
              {r.headline ? <HeadlinePill h={r.headline} className="rv-headline" />
                : r.risk && <span className={`rv-risk ${r.risk}`}>{r.risk.toUpperCase()}</span>}
              <span className={`rv-status ${r.status}`}>{LIVE.has(r.status) ? `${r.status}…` : r.status}</span>
              <span className="when">{ago(r.created_at)} · {r.created_by}</span>
            </Link>
          ))}
        </div>
        {rows && rows.length > 0 && (query || chip !== "all") && (
          <p className="rv-count">{shown.length} of {rows.length} reviews{query ? " · Esc clears" : ""}</p>
        )}
      </section>
    </main>
  );
}

function StartReview() {
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const cls = parseCls(text);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.createReview(cls, title.trim() || undefined);
      navigate(`/r/${r.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <Logo size={72} />
      <h1>Review a change</h1>
      <p>Shelved or submitted changelists, one or several; they're stacked in CL order.</p>
      <label>Changelists (shelved or submitted)
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="12345 12346" />
      </label>
      <div className="hint">{cls.length ? `Will analyse: ${cls.join(", ")}` : "Enter one or more CL numbers."}</div>
      <label>Title (optional)<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      {error && <div className="err">{error}</div>}
      <button className="go" disabled={!cls.length || busy}>{busy ? "Starting…" : "Start review"}</button>
      <div className="hint">The board opens on its own when the analysis finishes.</div>
    </form>
  );
}
