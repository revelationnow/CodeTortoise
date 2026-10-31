import { useContext, useState } from "react";
import { api, errorText } from "../api";
import { useViewer } from "../viewer";
import { WsContext } from "../workspace/context";

/** The owner's mark (spec 2026-10-09-shared-sinks §6.2): treat a field as a shared sink in every review of the workspace from
 * the next run, or stop. Inside a review it offers the re-run that applies it; `onDone` tells a list of marks to load again.
 * The workspace and the owner are the viewer's (spec 2026-10-31 §8): the review's, or the Health page's. */
export default function SinkMark({ label, on = false, onDone }: { label: string; on?: boolean; onDone?: () => void }) {
  const viewer = useViewer(), ws = useContext(WsContext);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!viewer?.is_owner) return null;
  const wid = viewer.workspace.id;
  const fail = (what: string) => (e: unknown) => setError(errorText(e, what));     // `what`: said when the server says nothing
  const act = () => {
    setError(null);                                // a new attempt clears the last failure, so a repeat is told again
    return (on ? api.unmarkSink(wid, label) : api.markSink(wid, label))
      .then(() => { setDone(true); onDone?.(); }, fail(`The field could not be ${on ? "unmarked" : "marked"} as a sink.`));
  };
  const rerun = () => {
    if (!ws) return;
    setBusy(true);
    setError(null);
    api.rerun(ws.data.id).then(ws.data.loadDetail).catch(fail("The server did not accept the re-run.")).finally(() => setBusy(false));
  };
  const warn = error && <span className="banner warn" role="alert">{error}</span>;
  if (done)
    return (
      <span className="sink-mark">{on ? "Unmarked" : "Marked"} — re-run to apply
        {ws && <> <button className="link" onClick={rerun} disabled={busy}>Re-run</button></>}
        {warn}
      </span>
    );
  return (
    <span className="sink-mark">
      {on ? <button className="link" onClick={act} aria-label={`Unmark ${label}`}>unmark {label}</button>
        : <button className="link" onClick={act} aria-label={`Treat ${label} as a sink`}
                  title="Hide this field's readers and writers in every review from the next run">Treat <code>{label}</code> as a sink</button>}
      {warn}
    </span>
  );
}
