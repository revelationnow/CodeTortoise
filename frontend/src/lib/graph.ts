import type { Edge, Impact } from "../api";

export type GraphMode = "before" | "after" | "diff";

export interface GraphElement { data: Record<string, unknown>; classes: string }

/** Nodes/edges of the given flows (or all changed flows) as cytoscape elements, filtered by mode. */
export function flowElements(impact: Impact, roots: string[], mode: GraphMode, showData: boolean): GraphElement[] {
  const edgeById = new Map(impact.edges.map((e) => [e.id, e]));
  const nodeIds = new Set<string>();
  const edges: Edge[] = [];
  for (const flow of impact.flows.filter((f) => roots.includes(f.root))) {
    flow.nodes.forEach((n) => nodeIds.add(n));
    flow.edges.forEach((id) => { const e = edgeById.get(id); if (e) edges.push(e); });
  }
  if (showData) {
    for (const e of impact.edges) {
      if ((e.kind === "writes" || e.kind === "reads") && roots.includes(e.src)) {
        edges.push(e);
        nodeIds.add(e.dst);
      }
    }
  }
  const visible = (e: Edge) => mode === "diff" || (mode === "after" ? e.status !== "removed" : e.status !== "added");
  const kept = [...new Map(edges.filter(visible).map((e) => [e.id, e])).values()];
  const used = new Set<string>(roots);
  kept.forEach((e) => { used.add(e.src); used.add(e.dst); });
  const out: GraphElement[] = [];
  for (const id of nodeIds) {
    if (!used.has(id)) continue;
    const n = impact.nodes[id];
    if (!n) continue;
    const status = mode === "diff" ? n.status : "unchanged";
    out.push({
      data: { id, label: n.label, layer: n.layer ?? -1 },
      classes: [n.kind, `st-${status}`, n.confidence === "heuristic" ? "heuristic" : "", roots.includes(id) ? "root" : ""].join(" ").trim(),
    });
  }
  for (const e of kept) {
    const status = mode === "diff" ? e.status : "unchanged";
    out.push({
      data: { id: e.id, source: e.src, target: e.dst, label: e.kind === "call" ? "" : e.kind },
      classes: [e.kind === "writes" || e.kind === "reads" ? "data" : "call", e.kind, `st-${status}`, `conf-${e.confidence}`].join(" "),
    });
  }
  return out;
}

/** Nodes grouped by blast hop ring, highest score first. */
export function blastRings(impact: Impact): Map<number, { id: string; score: number; via: string }[]> {
  const rings = new Map<number, { id: string; score: number; via: string }[]>();
  for (const b of impact.blast) {
    const ring = rings.get(b.hop) ?? [];
    ring.push({ id: b.node, score: b.score, via: b.via });
    rings.set(b.hop, ring);
  }
  for (const ring of rings.values()) ring.sort((a, b) => b.score - a.score);
  return rings;
}
