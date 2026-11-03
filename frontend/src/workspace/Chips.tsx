import { Link } from "react-router-dom";
import { causeOpen, firstOpenAt } from "../reading/causes";
import type { Cause, CheckKind } from "../reading/types";
import { useWs } from "./context";
import { Ticks } from "./NameText";
import { bare, plainNames } from "./names";

/** Check chips (spec 2026-10-16-outline-and-causes §2.3): one per shown cause, done ones muted with ✓; a chip opens the
 * stepper at the cause's first open place. A Flows group's, a flow's without places, the Flows tab's end line and a
 * story's without flows (spec 2026-10-25-review-ui-redesign §7). `muted`: kinds the reader hides; a check the design names
 * still shows, muted, as its words cite it (phase 2 minor 7). */
export default function Chips({ causes, muted }: { causes: Cause[]; muted?: ReadonlySet<CheckKind> }) {
  const ws = useWs(), d = ws.data, marks = d.reading?.marks ?? {};
  if (!causes.length) return null;
  return (
    <ul className="st-chips">{causes.map((c) => {
      const line = plainNames(c.text, d.names), done = !causeOpen(c, marks), quiet = !!muted?.has(c.kind);
      return (
        <li key={c.id}><Link className={`st-chip ${c.kind}${done ? " done" : ""}${quiet ? " muted" : ""}`}
                             to={ws.link(ws.opened({ cause: c.id, at: firstOpenAt(c, marks) }))} title={bare(line)}
                             aria-label={`Open check: ${bare(line)}${quiet ? " (a kind you hide)" : ""}`}>
          {done && <span aria-hidden>✓ </span>}<Ticks text={line} /></Link></li>
      );
    })}</ul>
  );
}
