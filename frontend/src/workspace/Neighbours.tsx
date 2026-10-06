import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Neighbour, type Neighbours as Model } from "../api";
import { keys, load, save } from "../board/prefs";
import FoldButton from "../components/FoldButton";
import { useWs } from "./context";

const LIMIT = 20;
const MAX = 500;                                             // the server lists at most this many of a side

const fileName = (path: string) => path.slice(path.lastIndexOf("/") + 1);

/** The Neighbours tab (spec 2026-10-04-review-workspace §3.7): callers, the node, callees, as stacked tiles or as the call
 * tree; a tile moves the panel to that node (a history entry, so Back returns). Replaces growing the board on "+N callers". */
export default function Neighbours({ nid }: { nid: string }) {
  const ws = useWs(), d = ws.data;
  const [more, setMore] = useState<{ callers?: number; callees?: number }>({});    // a column grown by Show all
  const [model, setModel] = useState<Model | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [view, setView] = useState<"tiles" | "tree">(() => (load<unknown>(keys.nbView, "tiles") === "tree" ? "tree" : "tiles"));
  const show = (v: "tiles" | "tree") => { setView(v); save(keys.nbView, v); };
  useEffect(() => {
    let live = true;
    setError(null);
    api.neighbours(d.id, nid, LIMIT, more).then((m) => { if (live) setModel(m); })
      .catch((e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [d.id, nid, more, tick]);
  if (error) return <div className="bd-note error">{error} <button className="bd-ibtn" onClick={() => setTick((t) => t + 1)}>Retry</button></div>;
  if (!model) return <div className="bd-note">Finding callers and callees…</div>;
  const row = (n: Neighbour) => {
    const where = n.path ? fileName(n.path) : null;
    return (
      <li key={n.id}>
        <Link to={ws.link(ws.opened({ node: n.id }, "neighbours"))} className={`ws-nb${n.test ? " test" : ""}`}
              title={`Open ${n.label}'s neighbours`} aria-label={`Open ${n.label}'s neighbours`}>
          <span className="ws-row-top"><b className="mono">{n.label}</b>
            {n.changed && <span className="ws-badge changed">changed</span>}
            {n.test && <span className="ws-badge">test</span>}
            {n.story && <span className="ws-handle">{n.story}</span>}</span>
          {where && <span className="ws-row-sub mono">{where}{n.line ? `:${n.line}` : ""}</span>}
        </Link>
      </li>
    );
  };
  const column = (title: string, key: "callers" | "callees") => {
    const side = model[key], all = Math.min(side.total, MAX);
    return (
      <section className="ws-nb-col" aria-label={title}>
        <h3>{title} <span className="muted small">{side.total}</span></h3>
        {side.items.length ? <ul>{side.items.map(row)}</ul> : <p className="muted small">None.</p>}
        {all > side.items.length && (
          <FoldButton icon="more" label={all === side.total ? `Show all ${side.total}` : `Show ${MAX} of ${side.total}`}
                      onClick={() => setMore((m) => ({ ...m, [key]: all }))} />
        )}
      </section>
    );
  };
  return (
    <div className="ws-nbs-wrap">
      <span className="bd-seg ws-nb-view" role="group" aria-label="Show neighbours as">
        {(["tiles", "tree"] as const).map((v) => (
          <button key={v} className={`bd-ibtn${view === v ? " on" : ""}`} aria-pressed={view === v} onClick={() => show(v)}>
            {v === "tiles" ? "Tiles" : "Tree"}</button>
        ))}
      </span>
      {view === "tree" ? <CallTree rid={d.id} root={model} /> : (
        <div className="ws-nbs">
          {column("Callers", "callers")}
          <span className="ws-nb-arrow" aria-hidden>↓</span>
          <section className="ws-nb-col me" aria-label="This function">
            <h3>This function</h3>
            <div className="ws-nb on"><b className="mono">{model.node.label}</b>
              {model.node.changed && <span className="ws-badge changed">changed</span>}
              {model.node.path && <span className="ws-row-sub mono">{fileName(model.node.path)}</span>}</div>
          </section>
          <span className="ws-nb-arrow" aria-hidden>↓</span>
          {column("Callees", "callees")}
        </div>
      )}
    </div>
  );
}

type Dir = "callers" | "callees";
type Got = { status: "loading" } | { status: "error"; error: string } | { status: "ok"; model: Model };
/** What the call tree has fetched (per review, by node) and which branches are open (per review and root, by the path from
 * the root): kept for the session, so leaving for a function's code and coming Back finds the tree as it was. */
const fetched = new Map<string, Got>();
const opened = new Map<string, Set<string>>();

/** The call tree (on demand): who reaches this function and what it reaches, one level per click. A branch only ever
 * lists the next callers (or callees) of the row it grew from — never a parent's other calls — and a function already on
 * the branch is marked instead of growing again. */
function CallTree({ rid, root }: { rid: number; root: Model }) {
  const ws = useWs();
  const memo = `${rid}:${root.node.id}`;
  const [open, setOpen] = useState(() => opened.get(memo) ?? new Set<string>());
  const [, redraw] = useState(0);
  fetched.set(`${rid}:${root.node.id}`, { status: "ok", model: root });
  const got = (id: string) => fetched.get(`${rid}:${id}`);
  const fetchOne = (id: string, more: { callers?: number; callees?: number } = {}) => {
    const k = `${rid}:${id}`;
    if (!Object.keys(more).length && fetched.get(k)?.status === "ok") return;
    if (!Object.keys(more).length) fetched.set(k, { status: "loading" });
    redraw((t) => t + 1);
    api.neighbours(rid, id, LIMIT, more).then((m) => fetched.set(k, { status: "ok", model: m }))
      .catch((e) => fetched.set(k, { status: "error", error: String(e.message ?? e) })).finally(() => redraw((t) => t + 1));
  };
  const toggle = (key: string, id: string) => {
    const next = new Set(open);
    if (next.has(key)) next.delete(key); else { next.add(key); fetchOne(id); }
    opened.set(memo, next);
    setOpen(next);
  };

  const kids = (dir: Dir, id: string, path: string[]) => {
    const g = got(id);
    if (!g || g.status === "loading") return <p className="muted small ws-tree-note">Finding {dir}…</p>;
    if (g.status === "error") return <p className="bd-note error ws-tree-note">{g.error} <button className="bd-ibtn" onClick={() => fetchOne(id)}>Retry</button></p>;
    const side = g.model[dir], all = Math.min(side.total, MAX);
    if (!side.items.length) return <p className="muted small ws-tree-note">None.</p>;
    return (
      <>
        <ul role="group">{side.items.map((n) => item(dir, n, path))}</ul>
        {all > side.items.length && <FoldButton icon="more" label={`Show all ${side.total} ${dir} of ${g.model.node.label}`}
                                                onClick={() => fetchOne(id, { [dir]: all })} />}
      </>
    );
  };
  const item = (dir: Dir, n: Neighbour, path: string[]) => {
    const here = [...path, n.id], key = `${dir}/${here.join(">")}`, loop = path.includes(n.id), on = open.has(key);
    const verb = dir === "callers" ? "callers" : "callees";
    return (
      <li key={n.id} role="treeitem" aria-label={n.label} aria-expanded={loop ? undefined : on} className="ws-tree-item">
        <div className="ws-tree-row">
          {loop ? <span className="ws-tree-tog" aria-hidden>↻</span>
            : <button className="ws-tree-tog" aria-label={`${on ? "Hide" : "Show"} ${n.label}'s ${verb}`}
                      title={`${on ? "Hide" : "Show"} ${n.label}'s ${verb}`} onClick={() => toggle(key, n.id)}>{on ? "▾" : "▸"}</button>}
          <Link className="ws-name ws-tree-name" to={ws.link(ws.opened({ node: n.id }))} title={`Open ${n.label}'s code`}
                aria-label={`Open ${n.label}'s code`}>{n.label}</Link>
          {n.changed && <span className="ws-badge changed">changed</span>}
          {n.test && <span className="ws-badge">test</span>}
          {loop ? <span className="muted small">already above</span>
            : n.path && <span className="ws-row-sub mono">{fileName(n.path)}{n.line ? `:${n.line}` : ""}</span>}
        </div>
        {on && !loop && kids(dir, n.id, here)}
      </li>
    );
  };
  const tree = (dir: Dir, title: string) => (
    <section className="ws-tree-sec">
      <h3>{title}</h3>
      <ul role="tree" aria-label={title} className="ws-tree">
        <li role="treeitem" aria-label={root.node.label} aria-expanded className="ws-tree-item root">
          <div className="ws-tree-row"><b className="mono">{root.node.label}</b>
            {root.node.changed && <span className="ws-badge changed">changed</span>}</div>
          {kids(dir, root.node.id, [root.node.id])}
        </li>
      </ul>
    </section>
  );
  return <div className="ws-trees">{tree("callers", "Called by")}{tree("callees", "Calls")}</div>;
}
