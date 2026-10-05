import { Fragment } from "react";
import { Link } from "react-router-dom";
import type { Crumb } from "./crumbs";

/** The centre's breadcrumb: `Review 7 › Stories › S1 frame_pop writes… › Graph`, every part above the current a link. */
export default function Crumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="ws-crumbs" aria-label="Breadcrumb">
      {items.map((c, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="sep" aria-hidden> › </span>}
          {c.to ? <Link to={c.to} title={`Go to ${c.label}`} aria-label={`Go to ${c.label}`}>{c.label}{c.handle && <span className="ws-handle">{c.handle}</span>}</Link>
            : <span aria-current="page">{c.label}{c.handle && <span className="ws-handle">{c.handle}</span>}</span>}
        </Fragment>
      ))}
    </nav>
  );
}

/** A phone page's top bar (§2.1): where it came from and what it is, "‹ Stories · S1 frame_pop writes…". */
export function PhoneBar({ back, title, handle }: { back: Crumb; title: string; handle?: string }) {
  return (
    <div className="ws-phonebar">
      <Link to={back.to ?? "."} aria-label={`Back to ${back.label}`} title={`Back to ${back.label}`}>‹ {back.label}</Link>
      <span className="sep" aria-hidden>·</span>
      <b>{handle && <span className="ws-handle">{handle}</span>}{title}</b>
    </div>
  );
}
