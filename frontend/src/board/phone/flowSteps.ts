/** The phone flow reader's step list (spec §13.3): one entry per node on the flow, with a marker and a one-line reason. */
import type { Board, BoardFlow, BoardNode } from "../types";

export type StepKind = "plain" | "chg" | "field" | "landing";
export interface Step { id: string; label: string; kind: StepKind; marker: string; reason: string; hasCode: boolean; node: BoardNode }

export function flowSteps(board: Board, flow: BoardFlow): Step[] {
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const layerName = (n: BoardNode) => board.layers.find((l) => l.level === n.layer)?.name ?? "unlayered";
  const firstAnn = (id: string, landing = false) => board.impacts.find((a) => a.node === id && (!landing || a.landing));
  const nodes = flow.path.map((id) => byId.get(id)).filter((n): n is BoardNode => !!n);
  return nodes.map((n, i) => {
    const base = { id: n.id, label: n.label, hasCode: !!(n.path && n.range), node: n };
    if (n.id === flow.lands || n.id === flow.fx_at)
      return { ...base, kind: "landing", marker: "!", reason: firstAnn(n.id, true)?.text ?? flow.effect };
    if (n.change)
      return { ...base, kind: "chg", marker: "Δ", reason: `Δ ${n.change.kind} +${n.change.add} −${n.change.rem}` };
    if (n.kind === "field") {
      const a = firstAnn(n.id);
      return { ...base, kind: "field", marker: "f", reason: a ? `field · ${a.text}` : "field" };
    }
    const next = nodes[i + 1], a = firstAnn(n.id);
    const reason = i === 0 ? `entry · ${layerName(n)}`
      : [next ? `calls ${next.label}` : "", a?.text ?? ""].filter(Boolean).join(" · ");
    return { ...base, kind: "plain", marker: String(i + 1), reason };
  });
}
