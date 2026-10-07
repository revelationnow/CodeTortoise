import { Link } from "react-router-dom";
import { plainTitle } from "../lib/markdown";
import { CHECK_ORDER, KIND_LABEL, placeOf } from "../reading/checks";
import { at, INDEX_TABS, type IndexTab } from "./address";
import CheckTile from "./CheckList";
import ClusterPage from "./ClusterPage";
import { useWs } from "./context";
import { INDEX_LABEL } from "./crumbs";
import { Ticks } from "./NameText";
import { MapSection } from "./WholePage";

/** The Index's tabs, as links so each tab has its address. */
export function IndexTabs({ tab }: { tab: IndexTab }) {
  const ws = useWs(), r = ws.data.reading, d = ws.data;
  const count: Partial<Record<IndexTab, number>> = {
    cls: d.detail?.cls.length, files: d.about?.tree.reduce((n, t) => n + t.files.length, 0), checks: r ? r.checks.length : undefined,
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

/** What the rail no longer lists (spec 2026-10-07-review-reading §11): the CLs, the files, every check by kind and the
 * map; a part of the map opens with the Map tab above it. */
export default function IndexPage({ tab, cid }: { tab: IndexTab; cid?: string }) {
  const ws = useWs(), d = ws.data, r = d.reading;
  if (tab === "map" && cid)
    return <div className="ix-frame"><div className="ix-bar"><IndexTabs tab="map" /></div><ClusterPage cid={cid} /></div>;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ix-page">
      <IndexTabs tab={tab} />
      {tab === "cls" && (
        <ul className="ix-list">{(d.detail?.cls ?? []).map((c) => {
          const first = plainTitle((c.description ?? "").trim().split("\n")[0]);
          const files = d.about?.cls.find((x) => x.cl === c.cl)?.file_count;
          return (
            <li key={c.cl}>
              <Link to={ws.link(ws.item({ kind: "cl", cl: c.cl }))} title={`Open CL ${c.cl}`} aria-label={`Open CL ${c.cl}`}><b>CL {c.cl}</b></Link>
              {c.user && <span className="muted"> {c.user}</span>}
              {!!files && <span className="muted small"> · {files} file{files === 1 ? "" : "s"}</span>}
              {first && <div className="ix-sub">{first}</div>}
            </li>
          );
        })}</ul>
      )}
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
      {tab === "checks" && r && <>
        <CheckTile ofTotal={false} groups={CHECK_ORDER.map((k) => ({ label: KIND_LABEL[k], checks: r.checks.filter((c) => c.kind === k) }))
          .filter((g) => g.checks.length)} />
        {r.cleared.length > 0 && (
          <section className="ws-tile" aria-label="Found no hazard">
            <h3>Found no hazard</h3>
            <ul className="ov-lines">{r.cleared.map((k) => (
              <li key={k.key}><Ticks text={k.text} />{placeOf(k) && <span className="mono small"> · <Ticks text={placeOf(k)} /></span>}</li>
            ))}</ul>
          </section>
        )}
      </>}
      {tab === "map" && <MapSection />}
    </div></div>
  );
}
