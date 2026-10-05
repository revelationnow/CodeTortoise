import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Story } from "../board/types";
import { load, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import { sections } from "../stories/stories";
import { type Place, samePlace } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";
import { bySeverity, litStories, storyCls } from "./rail";

export type Section = "changeset" | "stories" | "findings" | "files";
const OPEN_KEY = "ct.ws.rail.open", WIDTH_KEY = "ct.ws.railW";
const scrollKey = (rid: number) => `ct.ws.${rid}.railScroll`;

function loadOpen(): Record<Section, boolean> {
  const v = load<unknown>(OPEN_KEY, null), all = { changeset: true, stories: true, findings: true, files: false };
  return v && typeof v === "object" ? { ...all, ...(v as Partial<Record<Section, boolean>>) } : all;
}

/** The rail (spec 2026-10-04-review-workspace §2.2): everything in the review, the stories visibly drawn from the change
 * set. `show` names a section to open and scroll to (an address's #stories). */
export default function Rail({ show, onPick }: { show: string | null; onPick: () => void }) {
  const ws = useWs(), d = ws.data;
  const [open, setOpen] = useState(loadOpen);
  const [width, setWidth] = useState(() => { const w = load<unknown>(WIDTH_KEY, 280); return typeof w === "number" && w >= 200 && w <= 600 ? w : 280; });
  const [cl, setCl] = useState<number | null>(null);
  const box = useRef<HTMLElement>(null);
  const refs = useRef(new Map<string, HTMLElement>());
  const toggle = (s: Section, to = !open[s]) => setOpen((o) => { const n = { ...o, [s]: to }; save(OPEN_KEY, n); return n; });

  useEffect(() => {                                        // the rail's scroll position, per review
    const el = box.current, k = scrollKey(d.id);
    if (!el) return;
    el.scrollTop = load<number>(k, 0);
    const on = () => save(k, el.scrollTop);
    el.addEventListener("scroll", on, { passive: true });
    return () => el.removeEventListener("scroll", on);
  }, [d.id, d.ready]);
  useEffect(() => {
    if (!show || !(show in open)) return;
    toggle(show as Section, true);
    window.requestAnimationFrame(() => refs.current.get(show)?.scrollIntoView({ block: "start" }));
  }, [show]);                                              // eslint-disable-line react-hooks/exhaustive-deps

  const here = (p: Place) => (samePlace(p, ws.addr.place) ? "page" as const : undefined);
  const row = (place: Place, label: string, body: ReactNode, cls = "") => (
    <Link to={ws.link(ws.item(place))} className={`ws-row ${cls}`} aria-current={here(place)} title={label} aria-label={label}
          onClick={onPick}>{body}</Link>
  );
  const section = (s: Section, title: string, body: ReactNode) => (
    <section className="ws-sec" ref={(el) => { if (el) refs.current.set(s, el); }} aria-label={title}>
      <h2><button className="ws-sec-t" aria-expanded={open[s]} onClick={() => toggle(s)}>
        <span className="caret" aria-hidden>{open[s] ? "▾" : "▸"}</span>{title}</button></h2>
      {open[s] && body}
    </section>
  );
  const ss = d.stories, lit = ss ? litStories(ss, cl) : null;
  const story = (st: Story) => row({ kind: "story", sid: st.id, view: "steps" }, `Go to story ${st.id}: ${short(st.title)}`, <>
    <span className="ws-row-top">
      {st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
      <span className="ws-row-title"><Ticks text={st.title} /></span>
      <span className="ws-handle">{st.id}</span>
    </span>
    {st.cls.length > 0 && <span className="ws-chips">{st.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}</span>}
  </>, `story${lit && !lit.has(st.id) ? " dim" : ""}`);
  const group = (title: string, list: Story[]) => list.length > 0 && (
    <div className="ws-group"><h3>{title}</h3><ul>{list.map((st) => <li key={st.id}>{story(st)}</li>)}</ul></div>
  );
  const nFiles = d.about?.tree.reduce((n, t) => n + t.files.length, 0) ?? 0;
  const of = d.stories ? sections(d.stories) : null;
  const shown = ws.addr.open && "file" in ws.addr.open ? ws.addr.open.file : null;

  return (
    <aside className="ws-rail" ref={box} style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents">
      <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(WIDTH_KEY, w)} />
      <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={here({ kind: "whole" })}
            title="Go to the whole change" aria-label="Go to the whole change" onClick={onPick}>
        <span aria-hidden>⌂</span> Whole change {d.detail?.review.risk && <span className={`bd-pill ${d.detail.review.risk}`}>{d.detail.review.risk}</span>}
      </Link>
      {d.detail && section("changeset", `Change set (${d.detail.cls.length} CL${d.detail.cls.length === 1 ? "" : "s"})`, (
        <ul>{d.detail.cls.map((c) => {
          const first = (c.description ?? "").trim().split("\n")[0];
          const count = d.about?.cls.find((x) => x.cl === c.cl)?.file_count;
          const on = cl === c.cl;
          return (
            <li key={c.cl} className="ws-cl">
              {row({ kind: "cl", cl: c.cl }, `Open CL ${c.cl}`, <>
                <span className="ws-row-top"><b>CL {c.cl}</b><span className="muted">{c.user}</span>
                  {count !== undefined && <span className="muted small">{count} file{count === 1 ? "" : "s"}</span>}</span>
                <span className="ws-row-sub">{first}</span>
              </>)}
              {ss && <button className={`ws-dot${on ? " on" : ""}`} aria-pressed={on} onClick={() => setCl(on ? null : c.cl)}
                             title={on ? "Show every story" : `Highlight the stories drawn from CL ${c.cl}`}
                             aria-label={on ? "Show every story" : `Highlight the stories drawn from CL ${c.cl}`} />}
            </li>
          );
        })}</ul>
      ))}
      {ss && of && section("stories", `Stories (from ${storyCls(ss).length} CL${storyCls(ss).length === 1 ? "" : "s"})`, <>
        {group("What behaves differently", of.behaviour)}
        {of.collapsed.length > 0 && (
          <details className="ws-more"><summary>{of.collapsed.length} more behaviour stor{of.collapsed.length === 1 ? "y" : "ies"}</summary>
            <ul>{of.collapsed.map((st) => <li key={st.id}>{story(st)}</li>)}</ul></details>
        )}
        {group("Other changes", of.other)}
        {group("Repeated edits", of.mechanical)}
        {group("Tests", of.tests)}
        {!ss.stories.length && <p className="muted small">No changed functions.</p>}
      </>)}
      {d.ready && section("findings", `Findings (${d.findings.length})`, (
        bySeverity(d.findings).map((g) => (
          <div key={g.severity} className="ws-group"><h3>{g.severity}</h3><ul>{g.findings.map((f) => (
            <li key={f.id}>{row({ kind: "finding", fid: f.id }, `Go to finding ${f.id}: ${short(f.title)}`, <span className="ws-row-top">
              <span className={`ws-sev ${f.severity}`} aria-hidden />
              <span className="ws-row-title">{f.title}</span>
              <span className="ws-handle">{f.id}</span>
              {ss?.finding_story[f.id] && <span className="ws-handle">{ss.finding_story[f.id]}</span>}
            </span>, f.state !== "open" ? "done" : "")}</li>
          ))}</ul></div>
        ))
      ))}
      {d.about && section("files", `Files (${nFiles})`, (
        d.about.tree.map((t) => (
          <div key={t.dir} className="ws-group"><h3 className="mono">{t.dir}/</h3><ul>{t.files.map((f) => (
            <li key={f.path}>
              <Link to={ws.link(ws.opened({ file: f.path, line: null }, "diff"))} className="ws-row file" onClick={onPick}
                    aria-current={shown === f.path ? "true" : undefined} title={`Open ${f.name}'s diff`} aria-label={`Open ${f.name}'s diff`}>
                <span className="ws-row-top"><span className="mono">{f.name}</span><span className="muted small">{f.action}</span>
                  <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span></span>
                {f.cls.length > 0 && <span className="ws-chips">{f.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}</span>}
              </Link>
            </li>
          ))}</ul></div>
        ))
      ))}
    </aside>
  );
}
