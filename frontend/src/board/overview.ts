import type { ClusterInfo, Overview } from "./types";

/** The overview's layer bands (spec 2026-10-03-large-change-boards §5): each cluster in its layer, top layer first,
 * clusters without a layer in "other" at the bottom; layers without clusters are left out. */
export function bandsOf(ov: Overview): { level: number; name: string; clusters: ClusterInfo[] }[] {
  const levels = [...ov.layers].sort((a, b) => b.level - a.level);
  const other = levels.filter((l) => l.level < 0);
  return [...levels.filter((l) => l.level >= 0), ...other]
    .map((l) => ({ ...l, clusters: ov.clusters.filter((c) => (c.level ?? -1) === l.level) }))
    .filter((b) => b.clusters.length > 0);
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** A cluster's links in words, strongest first: "→ svc/logger: 22 calls, 3 shared fields" (it calls in) and
 * "← drv/uart: 9 calls" (it is called). `max` keeps the strongest few (phones). */
export function linkLines(ov: Overview, id: string, max = Infinity): string[] {
  const name = new Map(ov.clusters.map((c) => [c.id, c.name]));
  const lines = ov.links.filter((l) => l.src === id || l.dst === id).map((l) => {
    const out = l.src === id, other = name.get(out ? l.dst : l.src) ?? "?";
    const what = [l.calls ? plural(l.calls, "call", "calls") : "", l.fields ? plural(l.fields, "shared field", "shared fields") : ""]
      .filter(Boolean).join(", ");
    return { w: l.calls + l.fields, text: `${out ? "→" : "←"} ${other}: ${what}` };
  });
  return lines.sort((a, b) => b.w - a.w).slice(0, max).map((l) => l.text);
}

/** Clusters linked to `id` either way (outlined when it is selected). */
export function linkedTo(ov: Overview, id: string): Set<string> {
  return new Set(ov.links.flatMap((l) => (l.src === id ? [l.dst] : l.dst === id ? [l.src] : [])));
}

/** The previous or next cluster in risk order (‹ ›), wrapping around. */
export function stepCluster(ov: Overview, id: string, dir: 1 | -1): string {
  const i = ov.clusters.findIndex((c) => c.id === id), n = ov.clusters.length;
  return ov.clusters[((i < 0 ? 0 : i) + dir + n) % n].id;
}

/** The cluster whose changed code is in this depot file, or null. */
export function clusterOfFile(ov: Overview, path: string): string | null {
  return ov.clusters.find((c) => c.files.includes(path))?.id ?? null;
}
