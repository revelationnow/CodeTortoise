import { Link } from "react-router-dom";
import { plainTitle } from "../lib/markdown";
import { at, INDEX_TABS, type IndexTab } from "./address";
import ClusterPage from "./ClusterPage";
import { useWs } from "./context";
import FindingsIndex from "./FindingsIndex";
import { INDEX_LABEL } from "./crumbs";
import { MapSection } from "./WholePage";

/** The Index's tabs, as links so each tab has its address. */
export function IndexTabs({ tab }: { tab: IndexTab }) {
  const ws = useWs(), d = ws.data;
  const count: Partial<Record<IndexTab, number>> = {
    cls: d.detail?.cls.length, files: d.about?.tree.reduce((n, t) => n + t.files.length, 0),
    findings: d.findings.length,
  };
  return (
    <nav className="ws-switch ix-tabs" role="tablist" aria-label="Index">
      {INDEX_TABS.map((t) => (
        <Link key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""}
              to={ws.link(at({ kind: "index", tab: t }))}>{INDEX_LABEL[t]}{count[t] ? ` (${count[t]})` : ""}</Link>
      ))}
    </nav>
  );
}

/** Index › CLs (spec 2026-10-12-story-account-and-panels §5): each CL's files expand under it, and a file opens its diff
 * in the side panel, so the list stays. Which CLs are expanded lasts the visit. */
function ClsTab() {
  const ws = useWs(), d = ws.data, cls = d.detail?.cls ?? [];
  const files = d.about?.tree.flatMap((t) => t.files) ?? [];
  const open = ws.clsOpen, all = cls.length > 0 && cls.every((c) => open.has(c.cl));
  const flip = (cl: number) => {
    const next = new Set(open);
    if (!next.delete(cl)) next.add(cl);
    ws.setClsOpen(next);
  };
  return <>
    {cls.length > 0 && <div className="ix-tools">
      <button className="link" onClick={() => ws.setClsOpen(all ? new Set() : new Set(cls.map((c) => c.cl)))}>
        {all ? "Collapse all" : "Expand all"}</button></div>}
    <ul className="ix-list">{cls.map((c) => {
      const first = plainTitle((c.description ?? "").trim().split("\n")[0]);
      const count = d.about?.cls.find((x) => x.cl === c.cl)?.file_count;
      const mine = files.filter((f) => f.cls.includes(c.cl)), on = open.has(c.cl), verb = on ? "Hide" : "Show";
      return (
        <li key={c.cl}>
          <button className="bd-ibtn ix-exp" aria-expanded={on} aria-label={`${verb} CL ${c.cl}'s files`}
                  title={`${verb} CL ${c.cl}'s files`} onClick={() => flip(c.cl)}>{on ? "▾" : "▸"}</button>
          <Link to={ws.link(ws.item({ kind: "cl", cl: c.cl }))} title={`Open CL ${c.cl}`} aria-label={`Open CL ${c.cl}`}><b>CL {c.cl}</b></Link>
          {c.user && <span className="muted"> {c.user}</span>}
          {!!count && <span className="muted small"> · {count} file{count === 1 ? "" : "s"}</span>}
          {first && <div className="ix-sub">{first}</div>}
          {on && (mine.length ? <ul className="ix-files">{mine.map((f) => (
            <li key={f.path}>
              <Link className="mono" to={ws.link(ws.opened({ file: f.path, line: null, cl: c.cl }))}
                    title={`Open ${f.path}'s diff in CL ${c.cl}`} aria-label={`Open ${f.name}'s diff in CL ${c.cl}`}>{f.path}</Link>
              <span className="muted small"> {f.action}</span>
              <span className="cnt"> <span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
            </li>
          ))}</ul> : <p className="muted small ix-files">No files of this CL in the review's change summary.</p>)}
        </li>
      );
    })}</ul>
  </>;
}

/** What the rail no longer lists (spec 2026-10-07-review-reading §11): the CLs, the files, every check by kind and the
 * map; a part of the map opens with the Map tab above it. */
export default function IndexPage({ tab, cid }: { tab: IndexTab; cid?: string }) {
  const ws = useWs(), d = ws.data;
  if (tab === "map" && cid)
    return <div className="ix-frame"><div className="ix-bar"><IndexTabs tab="map" /></div><ClusterPage cid={cid} /></div>;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ix-page">
      <IndexTabs tab={tab} />
      {tab === "cls" && <ClsTab />}
      {tab === "files" && (d.about?.tree ?? []).map((t) => (
        <section key={t.dir} aria-label={`Files in ${t.dir}`} className="ix-dir">
          <h3 className="mono">{t.dir}/</h3>
          <ul className="ix-list">{t.files.map((f) => (
            <li key={f.path}>
              <Link className="mono" to={ws.link(ws.opened({ file: f.path, line: null }))} title={`Open ${f.name}'s diff`}
                    aria-label={`Open ${f.name}'s diff`}>{f.name}</Link>
              <span className="muted small"> {f.action}</span>
              <span className="cnt"> <span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
              {f.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}
            </li>
          ))}</ul>
        </section>
      ))}
      {tab === "findings" && <FindingsIndex />}
      {tab === "map" && <MapSection />}
    </div></div>
  );
}
