import type { Walk } from "../reading/types";
import { PAD, ROW, TOP, walkLayout } from "../reading/walks";

/** An arrow's head: a triangle with its point at (x, y), pointing right (`dir` 1) or left (-1). */
const head = (x: number, y: number, dir: 1 | -1) => `${x},${y} ${x - 7 * dir},${y - 4} ${x - 7 * dir},${y + 4}`;

/** A walk-through's sequence drawing (spec 2026-11-02-design-overview §4.4): an SVG in the board's colours, a column per
 * function under its component and a numbered row per step, in its own box that scrolls sideways when it is wider than the
 * page. The rows under it are the walk-through for the keyboard and for screen readers, so to them it is one image; a click
 * on a step opens its row. */
export default function WalkDrawing({ walk, label, component, open, onPick }: {
  walk: Walk; label: (n: string) => string; component: (n: string) => string | null; open: ReadonlySet<number>;
  onPick: (n: number) => void;
}) {
  const lay = walkLayout(walk, label, component);
  return (
    <figure className="dz-draw">
      <div className="dz-scroll">
        <svg role="img" aria-label={`The ${walk.steps.length} steps drawn in sequence; they are listed below`}
             width={lay.width} height={lay.height} viewBox={`0 0 ${lay.width} ${lay.height}`}>
          {lay.frames.map((f) => (
            <g key={f.y1} className="dz-frame">
              <rect x={f.x1} y={f.y1} width={f.x2 - f.x1} height={f.y2 - f.y1} rx={6} />
              <text x={f.x1 + 6} y={f.y1 + 12}>{f.text}{f.text !== `loop · ${f.full}` && <title>{f.full}</title>}</text>
            </g>
          ))}
          {lay.cols.map((c) => (
            <g key={c.node} className="dz-col">
              <text className="dz-fn" x={c.x} y={20} textAnchor="middle">{c.label}{c.label !== c.full && <title>{c.full}</title>}</text>
              {c.component && <text className="dz-comp" x={c.x} y={36} textAnchor="middle">{c.component}</text>}
              <line x1={c.x} y1={TOP - 8} x2={c.x} y2={lay.height - PAD / 2} />
            </g>
          ))}
          {lay.rows.map((r) => {
            const dir = r.x2 >= r.x1 ? 1 : -1, said = <>{r.text}{r.text !== r.full && <title>{r.full}</title>}</>;
            return (
              <g key={r.n} className={`dz-row ${r.status} ${r.line}`} onClick={() => onPick(r.n)}>
                <rect className="dz-hit" x={0} y={r.y - ROW / 2 - 4} width={lay.width} height={ROW} />
                <circle className={`dz-num${open.has(r.n) ? " open" : ""}`} cx={22} cy={r.y} r={10} />
                <text className="dz-numt" x={22} y={r.y + 4} textAnchor="middle">{r.n}</text>
                {r.loop ? <>
                  <path className="dz-line" d={`M ${r.x1} ${r.y - 6} h 26 v 12 h -18`} />
                  <polygon className="dz-head" points={head(r.x1 + 1, r.y + 6, -1)} />
                  <text className="dz-say" x={r.x1 + 32} y={r.y + 4}>{said}</text>
                </> : <>
                  <line className="dz-line" x1={r.x1} y1={r.y} x2={r.x2 - 6 * dir} y2={r.y} />
                  <polygon className="dz-head" points={head(r.x2, r.y, dir)} />
                  <text className="dz-say" x={(r.x1 + r.x2) / 2} y={r.y - 6} textAnchor="middle">{said}</text>
                </>}
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="dz-legend">
        <span className="dz-key new">new in the change</span>
        <span className="dz-key changed">changed</span>
        <span className="dz-key same">unchanged</span>
        <span className="dz-key open">a step with an open check</span>
      </figcaption>
    </figure>
  );
}
