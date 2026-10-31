import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText, type HealthCheck, type WorkspaceFields, type WorkspaceRow } from "../api";
import { useMe } from "../App";
import { EMPTY, type FormState, formErrors, fromFields, toBody, withDetected } from "../lib/workspaceForm";

type Checked = WorkspaceRow & { checks: HealthCheck[] };

/** The Workspaces page (spec 2026-10-31 §9): the workspaces on the session's servers with their status; an owner adds one
 * (saved even when its checks fail, §11) and edits, removes, rebuilds the index of and opens the Health page of their own. */
export default function Workspaces() {
  const me = useMe();
  const [rows, setRows] = useState<WorkspaceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | "new" | null>(null);          // the workspace whose form is open, or a new one
  const [saved, setSaved] = useState<Checked | null>(null);               // what the last add or edit answered
  const load = () => api.workspaces().then((w) => { setRows(w); setError(null); })
    .catch((e) => setError(errorText(e, "The workspaces could not be loaded.")));
  useEffect(() => { load(); }, []);
  const done = (w: Checked) => { setSaved(w); setOpen(null); load(); };
  const edit = (to: number | "new") => { setSaved(null); setOpen(to); };

  return (
    <main className="page">
      <div className="wsp-head">
        <h1>Workspaces</h1>
        {!!me?.owner_of.length && open !== "new" && <button onClick={() => edit("new")}>Add workspace</button>}
      </div>
      {saved && <SavedNote w={saved} signedIn={!!me?.logins.some((l) => l.server === saved.server)} />}
      {open === "new" && <WorkspaceForm initial={EMPTY} verb="Add" submit={api.addWorkspace} onDone={done} onCancel={() => setOpen(null)} />}
      {error && <p className="error" role="alert">{error}</p>}
      {!rows && !error && <p className="muted">Loading…</p>}
      <ul className="wsp-list">
        {rows?.map((w) => (
          <li key={w.id} className="wsp-row">
            <div className="wsp-main">
              <b>{w.name}</b>
              <span className="muted small">{w.server}{w.client ? ` · ${w.client}` : ""}</span>
              <span className={`hc-pill ${w.ready ? "ok" : "bad"}`}>● {w.ready ? "ready" : "not ready"}</span>
              {w.seed && <span className="muted small">set in tortoise.yaml</span>}
            </div>
            {!w.ready && w.reason && <div className="wsp-reason mono small">{w.reason}</div>}
            {(w.is_owner || w.can_manage) && <Actions w={w} onEdit={() => edit(w.id)} onChanged={load} />}
            {open === w.id && w.fields && (
              <WorkspaceForm initial={fromFields(w.fields)} verb="Save" submit={(body) => api.editWorkspace(w.id, body)} onDone={done}
                             onCancel={() => setOpen(null)} />
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}

/** What an add or an edit answered (§11: saved even when its checks fail), and the sign-in its server still needs. */
function SavedNote({ w, signedIn }: { w: Checked; signedIn: boolean }) {
  const failed = w.checks.filter((c) => c.hard && !c.ok);
  return (
    <div className={`banner wsp-saved${w.ready ? "" : " warn"}`} role="status">
      {w.ready ? `${w.name} is ready.`
        : `${w.name} is saved but not ready: ${w.reason}. Fix it on this host, then press Recheck on its Health page.`}
      {failed.length > 0 && <ul className="small">{failed.map((c) => <li key={c.name}><b>{c.name}</b>: {c.detail}</li>)}</ul>}
      {!signedIn && (
        <p><Link to={`/login?server=${encodeURIComponent(w.server)}&next=/workspaces`}>Sign in to {w.server}</Link> to see it and
          start reviews in it.</p>
      )}
    </div>
  );
}

/** An owner's tools on one workspace: its Health page and Rebuild index, and for one added here, Edit and Remove — which
 * the owner of the seed also gets on every workspace, so one saved with a server or user nobody signs in as is fixed. */
function Actions({ w, onEdit, onChanged }: { w: WorkspaceRow; onEdit: () => void; onChanged: () => void }) {
  const [msg, setMsg] = useState<{ text: string; failed?: boolean } | null>(null);
  const run = (act: () => Promise<unknown>, ok: string | null, failed: string) => {   // a new press clears the last answer
    setMsg(null);
    act().then(() => { if (ok) setMsg({ text: ok }); onChanged(); }).catch((e) => setMsg({ text: errorText(e, failed), failed: true }));
  };
  const remove = () => {
    if (window.confirm(`Remove the workspace ${w.name}? Its symbol index and settings are deleted.`))
      run(() => api.removeWorkspace(w.id), null, "The workspace could not be removed.");
  };
  return (
    <div className="wsp-acts">
      {w.is_owner && <Link to={`/workspaces/${w.id}`}>Health</Link>}
      {w.is_owner && (
        <button onClick={() => run(() => api.rebuildIndex(w.id), "Index rebuild queued", "The index rebuild could not be queued.")}>
          Rebuild index</button>
      )}
      {w.can_manage && !w.seed && <button onClick={onEdit}>Edit</button>}
      {w.can_manage && !w.seed && <button onClick={remove}>Remove</button>}
      {msg && <span className={msg.failed ? "error" : "muted"} role={msg.failed ? "alert" : "status"}>{msg.text}</span>}
    </div>
  );
}

/** Add or edit a workspace (spec 2026-10-31 §9): what the server would refuse shows once Add or Save is pressed. */
function WorkspaceForm({ initial, verb, submit, onDone, onCancel }: {
  initial: FormState; verb: "Add" | "Save"; submit: (body: WorkspaceFields) => Promise<Checked>; onDone: (w: Checked) => void;
  onCancel: () => void;
}) {
  const [f, setF] = useState(initial);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);              // what "Fill from root" could not read
  const errs = formErrors(f);
  const set = (k: keyof FormState) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const v = e.target.value;
    setF((now) => ({ ...now, [k]: v }));
  };
  const fill = () => {
    setError(null);
    api.detect(f.root.trim()).then((d) => { setF((now) => withDetected(now, d)); setNotes(d.notes); })
      .catch((e) => setError(errorText(e, "Nothing could be read at that root.")));
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await submit(toBody(f)));
    } catch (err) {
      setError(errorText(err, "The workspace could not be saved."));
      setBusy(false);
    }
  }
  const bad = (k: keyof FormState) => (tried && errs[k] ? <div className="wsp-bad">{errs[k]}</div> : null);
  const text = (k: keyof FormState, label: string) => (
    <>
      <label>{label}<input value={f[k]} onChange={set(k)} aria-invalid={tried && !!errs[k]} /></label>
      {bad(k)}
    </>
  );

  return (
    <form className="card stack wsp-form" onSubmit={save} aria-label={verb === "Add" ? "Add workspace" : `Edit ${initial.name}`}>
      {text("name", "Name")}
      <label>Version control
        <select value={f.vcs} onChange={set("vcs")}><option value="p4">Perforce</option><option value="git">Git</option></select>
      </label>
      {text("p4port", "Perforce server (P4PORT)")}
      {text("client", "Client")}
      {text("p4user", "User")}
      <div className="hint">The Perforce user its reads run as. Whoever signs in to its server as this user owns it.</div>
      <div className="wsp-root">
        <label>Root on this host<input value={f.root} onChange={set("root")} aria-invalid={tried && !!errs.root} /></label>
        <button type="button" onClick={fill} disabled={!f.root.trim().startsWith("/")}>Fill from root</button>
      </div>
      {bad("root")}
      {notes.map((n) => <div key={n} className="hint">{n}</div>)}
      <label>Compile database<textarea rows={2} value={f.compile_commands} onChange={set("compile_commands")} /></label>
      <div className="hint">auto, or the path of a compile_commands.json (one per line for several)</div>
      {text("swarm_url", "Swarm URL")}
      <details className="wsp-adv">
        <summary>Advanced</summary>
        <div className="stack">
          {text("build_root", "Build root")}
          <label>Settings<textarea rows={8} value={f.settings} onChange={set("settings")} spellCheck={false} /></label>
          <div className="hint">tortoise.yaml's toolchain, targets and analysis keys, as YAML</div>
        </div>
      </details>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="wsp-btns">
        <button className="go" disabled={busy}>{busy ? "Checking…" : verb}</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
