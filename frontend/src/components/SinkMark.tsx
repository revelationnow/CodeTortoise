import { useContext, useState } from "react";
import { api } from "../api";
import { useMe } from "../App";
import { WsContext } from "../workspace/context";

/** The owner's mark (spec 2026-10-09-shared-sinks §6.2): treat a field as a shared sink in every review from the next
 * run, or stop. Inside a review it offers the re-run that applies it. */
export default function SinkMark({ label, on = false }: { label: string; on?: boolean }) {
  const me = useMe(), ws = useContext(WsContext);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me?.is_owner) return null;
  const act = () => (on ? api.unmarkSink(label) : api.markSink(label))
    .then(() => setDone(true), (e) => setError(String(e.message ?? e)));
  if (done)
    return (
      <span className="sink-mark">{on ? "Unmarked" : "Marked"} — re-run to apply
        {ws && <> <button className="link" onClick={() => api.rerun(ws.data.id).then(ws.data.loadDetail)}>Re-run</button></>}
      </span>
    );
  return (
    <span className="sink-mark">
      {on ? <button className="link" onClick={act} aria-label={`Unmark ${label}`}>unmark {label}</button>
        : <button className="link" onClick={act} aria-label={`Treat ${label} as a sink`}
                  title="Hide this field's readers and writers in every review from the next run">Treat <code>{label}</code> as a sink</button>}
      {error && <span className="banner warn">{error}</span>}
    </span>
  );
}
