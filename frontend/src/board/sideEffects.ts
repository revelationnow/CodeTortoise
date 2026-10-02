/** "Files with side effects" (spec §13.7): files holding functions the change did not modify but that carry annotations,
 * grouped by directory under the same prefix as the change tree. */
import type { Annotation, Board } from "./types";

export interface AffectedFn { node: string; label: string; line: number; severity: Annotation["severity"]; landing: boolean; text: string }
export interface AffectedFile { path: string; name: string; alsoChanged: boolean; warn: number; fns: AffectedFn[] }
export interface AffectedDir { dir: string; files: AffectedFile[] }

const RANK = (a: Annotation) => (a.landing ? 0 : a.severity === "warn" ? 1 : a.severity === "info" ? 2 : 3);

export function sideEffectFiles(board: Board): AffectedDir[] {
  const nodes = new Map(board.nodes.map((n) => [n.id, n]));
  const changedFiles = new Set(board.about.tree.flatMap((d) => d.files.map((f) => f.path)));
  const first = board.about.tree[0]?.files[0], firstDir = board.about.tree[0]?.dir;
  const prefix = first ? first.path.slice(0, first.path.length - (firstDir === "." ? first.name : `${firstDir}/${first.name}`).length) : "";
  const byPath = new Map<string, Annotation[]>();
  for (const a of board.impacts) {
    const n = nodes.get(a.node);
    if (!a.path || !n || n.change || n.kind !== "function") continue;
    byPath.set(a.path, [...(byPath.get(a.path) ?? []), a]);
  }
  const files: (AffectedFile & { dir: string; best: number })[] = [...byPath].map(([path, anns]) => {
    const perNode = new Map<string, Annotation>();
    for (const a of [...anns].sort((x, y) => RANK(x) - RANK(y) || x.line - y.line))
      if (!perNode.has(a.node)) perNode.set(a.node, a);
    const rel = prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path;
    const cut = rel.lastIndexOf("/");
    return {
      path, name: rel.slice(cut + 1), dir: cut > 0 ? rel.slice(0, cut) : ".", alsoChanged: changedFiles.has(path),
      warn: anns.filter((a) => a.severity === "warn").length, best: Math.min(...anns.map(RANK)),
      fns: [...perNode.values()].sort((x, y) => x.line - y.line).map((a) => ({
        node: a.node, label: nodes.get(a.node)!.label, line: a.line, severity: a.severity, landing: a.landing, text: a.text })),
    };
  });
  const dirs = new Map<string, AffectedFile[]>();
  for (const f of files.sort((a, b) => a.best - b.best || (a.path < b.path ? -1 : 1))) {
    const { dir, best: _best, ...file } = f;
    dirs.set(dir, [...(dirs.get(dir) ?? []), file]);
  }
  return [...dirs].sort(([a], [b]) => (a < b ? -1 : 1)).map(([dir, fs]) => ({ dir, files: fs }));
}
