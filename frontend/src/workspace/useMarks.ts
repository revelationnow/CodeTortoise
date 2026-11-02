import { useState } from "react";
import { api, errorText } from "../api";
import { useWs } from "./context";

/** Marking checks fine for everyone and reopening them (spec 2026-10-25-review-ui-redesign §7.3), as a Flows row's tick
 * box and a walk-through step's do (spec 2026-11-02 §4.3): one at a time, each reloading the reading and the reader's ticks.
 * Each settles to whether the change landed and never rejects, so F says "Marked fine" only for a mark that did; a refusal's
 * words are in `error`, and one that comes without words says what the reader was doing. */
export default function useMarks() {
  const d = useWs().data;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = (act: () => Promise<unknown>, failed: string): Promise<boolean> => {
    if (busy) return Promise.resolve(false);                                   // one mark at a time; the tick boxes stay enabled, so they keep their focus
    setBusy(true);
    setError(null);
    return act().then(() => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})])).then(() => true)
      .catch((e) => { setError(errorText(e, failed)); return false; }).finally(() => setBusy(false));
  };
  const fine = (keys: string[]) => run(() => api.markChecks(d.id, keys), "The server did not accept the mark.");
  const reopen = (keys: string[]) => run(() => api.unmarkChecks(d.id, keys),   // all of them or none, so a refusal leaves the row as it was
                                         "The server did not reopen these checks.");
  return { busy, error, fine, reopen };
}
