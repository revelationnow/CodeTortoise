import { Fragment } from "react";

/** Renders text, turning node ids (N12) and finding ids (F3) into clickable chips. */
export default function CiteText({ text, onCite }: { text: string; onCite: (id: string) => void }) {
  const parts = text.split(/\b([NF]\d+)\b/);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <button key={i} className="cite" onClick={() => onCite(p)}>{p}</button>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

export function CiteList({ ids, onCite }: { ids: string[]; onCite: (id: string) => void }) {
  if (!ids.length) return null;
  return (
    <span className="cites">
      {ids.map((id) => <button key={id} className="cite" onClick={() => onCite(id)}>{id}</button>)}
    </span>
  );
}
