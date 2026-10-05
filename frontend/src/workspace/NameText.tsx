import { Fragment } from "react";
import { Link } from "react-router-dom";
import { useWs } from "./context";
import { short } from "./crumbs";
import { nameParts } from "./names";

/** Text with node ids shown as names linked to their code, and finding ids linked to their pages (spec §2.4). */
export default function NameText({ text }: { text: string }) {
  const ws = useWs();
  return (
    <>
      {nameParts(text, ws.data.names, ws.data.findings.map((f) => f.id)).map((p, i) => {
        if ("text" in p) return <Fragment key={i}>{p.text}</Fragment>;
        if ("code" in p) return <code key={i}>{p.code}</code>;
        if ("node" in p)
          return (
            <Link key={i} className="ws-name" to={ws.link(ws.opened({ node: p.node }))}
                  title={`Open ${p.label}'s code`} aria-label={`Open ${p.label}'s code`}>{p.label}</Link>
          );
        const f = ws.data.findings.find((x) => x.id === p.finding);
        const where = `Go to finding ${p.finding}${f ? `: ${short(f.title)}` : ""}`;
        return (
          <Link key={i} className="ws-handle link" to={ws.link(ws.item({ kind: "finding", fid: p.finding }))}
                title={where} aria-label={where}>{p.finding}</Link>
        );
      })}
    </>
  );
}

/** `code` spans for the backticked names in a title. */
export function Ticks({ text }: { text: string }) {
  return <>{text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}</>;
}
