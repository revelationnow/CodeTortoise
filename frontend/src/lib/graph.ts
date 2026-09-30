import type { Edge, Impact } from "../api";

export type GraphMode = "before" | "after" | "diff";

export interface GraphElement { data: Record<string, unknown>; classes: string }

export interface FlowOptions {
  /** Drop nodes whose file lives under tests/, test/ or fuzzers/ (changed roots are always kept). */
  hideTests?: boolean;
  /** Show at most this many callers per node; the rest collapse into one "+N more callers" node. */
  maxCallers?: number;
  /** Show at most this many callees per node; the rest collapse into one "+N more callees" node. */
  maxCallees?: number;
  /** Drop nodes more than this many edges away from the roots. */
  depth?: number;
}

const TEST_PATH = /(^|\/)(tests?|testing|fuzzers?)\//;

/** Nodes/edges of the given flows (or all changed flows) as cytoscape elements, filtered by mode. */
export function flowElements(impact: Impact, roots: string[], mode: GraphMode, showData: boolean,
                             opts: FlowOptions = {}): GraphElement[] {
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
  const isTest = (id: string) => !roots.includes(id) && TEST_PATH.test(impact.nodes[id]?.file ?? "");
  const visible = (e: Edge) => (mode === "diff" || (mode === "after" ? e.status !== "removed" : e.status !== "added"))
    && !(opts.hideTests && (isTest(e.src) || isTest(e.dst)));
  let kept = [...new Map(edges.filter(visible).map((e) => [e.id, e])).values()];
  if (opts.depth !== undefined) {
    const dist = new Map<string, number>(roots.map((r) => [r, 0]));
    const queue = [...roots];
    while (queue.length) {
      const n = queue.shift()!;
      for (const e of kept) {
        const other = e.src === n ? e.dst : e.dst === n ? e.src : null;
        if (other !== null && !dist.has(other)) {
          dist.set(other, dist.get(n)! + 1);
          queue.push(other);
        }
      }
    }
    const near = (id: string) => (dist.get(id) ?? Infinity) <= opts.depth!;
    kept = kept.filter((e) => near(e.src) && near(e.dst));
  }
  // keep changed endpoints first, then precise ones, then by label
  const byRank = (pick: (e: Edge) => string) => (a: Edge, b: Edge) => rank(impact, pick(a)) - rank(impact, pick(b))
    || impact.nodes[pick(a)].label.localeCompare(impact.nodes[pick(b)].label);
  const cap = (limit: number | undefined, key: (e: Edge) => string, other: (e: Edge) => string) => {
    const out = new Map<string, number>();
    if (limit === undefined) return out;
    const groups = new Map<string, Edge[]>();
    for (const e of kept) if (e.kind === "call" || e.kind === "virtual") groups.set(key(e), [...(groups.get(key(e)) ?? []), e]);
    const drop = new Set<string>();
    for (const [k, group] of groups) {
      if (group.length <= limit) continue;
      [...group].sort(byRank(other)).slice(limit).forEach((e) => drop.add(e.id));
      out.set(k, group.length - limit);
    }
    kept = kept.filter((e) => !drop.has(e.id));
    return out;
  };
  const collapsed = cap(opts.maxCallers, (e) => e.dst, (e) => e.src);
  const collapsedOut = cap(opts.maxCallees, (e) => e.src, (e) => e.dst);
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
  for (const [target, n] of collapsed) {
    out.push({ data: { id: `more:${target}`, label: `+${n} more callers` }, classes: "more" });
    out.push({ data: { id: `more-edge:${target}`, source: `more:${target}`, target, label: "" }, classes: "call more" });
  }
  for (const [source, n] of collapsedOut) {
    out.push({ data: { id: `more-out:${source}`, label: `+${n} more callees` }, classes: "more" });
    out.push({ data: { id: `more-out-edge:${source}`, source, target: `more-out:${source}`, label: "" }, classes: "call more" });
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

function rank(impact: Impact, id: string): number {
  const n = impact.nodes[id];
  if (!n) return 3;
  if (n.status !== "unchanged") return 0;
  return n.confidence === "precise" ? 1 : 2;
}
