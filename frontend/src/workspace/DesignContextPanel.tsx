import { type ChangeEvent, type CSSProperties, useEffect, useState } from "react";
import { api, type DesignContext, type DesignContextView, errorText } from "../api";
import { useViewer } from "../viewer";
import { useWs } from "./context";
import { CAP, componentsText, contextChars, docName, EMPTY_CONTEXT, linkName, MAX, noteSentence, parseComponents } from "./designContext";
import { Ticks } from "./NameText";

const FILE_MAX = 1_000_000;    // a file read in the browser, as a link the server reads (§14): more than the context holds

/** The design context panel (spec 2026-11-02 §8): what the code can't say — notes, documents, conditions added or left
 * out by hand, and a choice of components. The owner edits and saves it, which re-runs the design stage alone; anyone
 * else in the review reads it. The AI's opening reads it; the checks never do. */
export default function DesignContextPanel({ style }: { style: CSSProperties }) {
  const ws = useWs(), d = ws.data, me = useViewer(), owner = !!me?.is_owner;
  const [view, setView] = useState<DesignContextView | null>(null);
  const [c, setC] = useState<DesignContext>(EMPTY_CONTEXT);
  const [comps, setComps] = useState("");
  const [link, setLink] = useState("");
  const [test, setTest] = useState("");
  const [fn, setFn] = useState("");
  const [error, setError] = useState("");
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.designContext(d.id).then((v) => { setView(v); setC(v.context); setComps(componentsText(v.context.components)); },
                                 (e) => setError(errorText(e, "The design context could not be loaded.")));
  }, [d.id]);
  const design = d.reading?.design ?? null;
  const found = (design?.gates ?? []).filter((g) => g.source === "code" && !c.conditions.remove.includes(g.test));
  const parsed = parseComponents(comps), chars = contextChars(c), cap = view?.cap ?? CAP;
  const set = (part: Partial<DesignContext>) => { setC({ ...c, ...part }); setSaid(""); };
  const conds = c.conditions;
  const docsFull = c.documents.length >= MAX.documents, addFull = conds.add.length >= MAX.add;
  const removeFull = conds.remove.length >= MAX.remove, compsOver = parsed.components.length > MAX.components;
  const addFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > FILE_MAX) { setError(`${file.name} holds more than 1 MB; the design context holds at most 12,000 characters.`); return; }
    setError("");
    file.text().then((text) => { setC((cur) => ({ ...cur, documents: [...cur.documents, { name: docName(file.name), text, url: null }] })); setSaid(""); },
                     () => setError(`${file.name} could not be read.`));
  };
  const save = () => {
    setBusy(true);
    setError("");
    api.saveDesignContext(d.id, { ...c, components: parsed.components })
      .then(() => { setSaid("Saved. The overview reads it now."); d.awaitDesign(); })
      .catch((e) => setError(errorText(e, "The design context could not be saved.")))
      .finally(() => setBusy(false));
  };
  return (
    <div className="rm-panel dc-panel" role="dialog" aria-label="Design context" tabIndex={-1} style={style}>
      <h2>Design context</h2>
      <p className="muted small">What the code can't say: what the change is for, the documents behind it, the conditions
        that matter. The AI's opening reads it; the checks never do.</p>
      {error && <div className="banner error" role="alert">{error}</div>}
      {!view ? !error && <p className="muted">Loading…</p> : !owner ? (
        <div className="dc-read">
          {view.context.notes ? <p className="dc-text">{view.context.notes}</p> : <p className="muted">No notes.</p>}
          {view.context.documents.map((doc, i) => <p key={`${doc.name}-${i}`} className="small">Document: {doc.name}</p>)}
          {view.context.conditions.add.map((h) => <p key={h.test} className="small">Condition added: <code>{h.test}</code></p>)}
          {view.context.conditions.remove.map((t) => <p key={t} className="small">Condition left out: <code>{t}</code></p>)}
          {view.context.components.length > 0 && <pre className="small">{componentsText(view.context.components)}</pre>}
        </div>
      ) : (
        <div className="dc-form">
          <label>Notes<textarea rows={5} value={c.notes} onChange={(e) => set({ notes: e.target.value })} /></label>
          <div className="dc-docs">
            {c.documents.length > 0 && <ul>{c.documents.map((doc, i) => (
              <li key={`${doc.name}-${i}`}>{doc.name}{doc.url && !doc.text ? " (read when saved)" : ` · ${[...doc.text].length} characters`}
                {" "}<button className="link" aria-label={`Remove ${doc.name}`}
                                    onClick={() => set({ documents: c.documents.filter((_, k) => k !== i) })}>Remove</button></li>
            ))}</ul>}
            <label>Add a file<input type="file" accept=".md,.markdown,.txt,text/plain,text/markdown" disabled={docsFull} onChange={addFile} /></label>
            {view.links && <div className="dc-row">
              <label>Link<input type="url" value={link} placeholder="https://" maxLength={2000} onChange={(e) => setLink(e.target.value)} /></label>
              <button disabled={!link.trim() || docsFull}
                      onClick={() => { set({ documents: [...c.documents, { name: linkName(link), text: "", url: link.trim() }] }); setLink(""); }}>
                Add the link</button>
            </div>}
            {docsFull && <p className="muted small">The context holds at most {MAX.documents} documents; remove one to add another.</p>}
          </div>
          <div className="dc-conds">
            <h3>Conditions</h3>
            {found.length > 0 && <ul>{found.map((g) => (
              <li key={g.id}><code>{g.test}</code>{" "}
                <button className="link" aria-label={`Leave out ${g.test}`} disabled={removeFull}
                        onClick={() => set({ conditions: { ...conds, remove: [...conds.remove, g.test] } })}>Leave out</button></li>
            ))}</ul>}
            {removeFull && <p className="muted small">The context leaves out at most {MAX.remove} conditions.</p>}
            {conds.remove.length > 0 && <ul>{conds.remove.map((t) => (
              <li key={t}>Left out: <code>{t}</code>{" "}
                <button className="link" aria-label={`Put back ${t}`}
                        onClick={() => set({ conditions: { ...conds, remove: conds.remove.filter((x) => x !== t) } })}>Put back</button></li>
            ))}</ul>}
            {conds.add.length > 0 && <ul className="dc-added">{conds.add.map((h, i) => (
              <li key={`${h.test}-${i}`}>Added: <code>{h.test}</code>{h.function && <> in <code>{h.function}</code></>}{" "}
                <button className="link" aria-label={`Remove the condition ${h.test}`}
                        onClick={() => set({ conditions: { ...conds, add: conds.add.filter((_, k) => k !== i) } })}>Remove</button></li>
            ))}</ul>}
            <div className="dc-row">
              <label>Condition, as the code writes it<input value={test} placeholder="len > 64" maxLength={300} onChange={(e) => setTest(e.target.value)} /></label>
              <label>In the function (optional)<input value={fn} maxLength={200} onChange={(e) => setFn(e.target.value)} /></label>
              <button disabled={!test.trim() || addFull} onClick={() => {
                set({ conditions: { ...conds, add: [...conds.add, { test: test.trim(), function: fn.trim() || null }] } });
                setTest(""); setFn("");
              }}>Add the condition</button>
            </div>
            {addFull && <p className="muted small">The context holds at most {MAX.add} added conditions.</p>}
            {(design?.context_notes.length ?? 0) > 0 && <ul className="dc-notes">{design!.context_notes.map((n) => (
              <li key={n}><Ticks text={noteSentence(n)} /></li>
            ))}</ul>}
          </div>
          <label>Components<textarea rows={4} value={comps} placeholder={"Driver: driver/**\nHAL: hal/**, include/hal/**"}
                                     onChange={(e) => { setComps(e.target.value); setSaid(""); }} /></label>
          <p className="muted small">A line each: a name, a colon, and the files it holds as globs. None: the workspace's own.
            {parsed.bad.length > 0 && <> Not read: {parsed.bad.join("; ")}.</>}
            {compsOver && <> The context holds at most {MAX.components} components.</>}</p>
          <p className={`dc-count small${chars > cap ? " over" : ""}`}>{chars.toLocaleString("en-US")} of {cap.toLocaleString("en-US")} characters</p>
          <div className="dc-acts">
            <button onClick={save} disabled={busy || chars > cap || parsed.bad.length > 0 || compsOver}>{busy ? "Saving…" : "Save"}</button>
            <span role="status" className="muted small">{said && (d.designing ? "Saved. The design stage is running…" : said)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
