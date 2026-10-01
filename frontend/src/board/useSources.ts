import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type FileChange } from "../api";
import type { SourceText } from "./types";

export type SourceState =
  | { status: "loading" }
  | { status: "ok"; file: SourceText }
  | { status: "error"; error: string };

/** Text of any file the board shows: changed files come from the change set; others are fetched on demand
 * (`GET /source`, i.e. p4 print at the workspace's have revision) and kept for the session. */
export function useSources(reviewId: number, files: FileChange[]) {
  const changed = useRef(new Map<string, FileChange>());
  changed.current = new Map(files.map((f) => [f.depot, f]));
  const [fetched, setFetched] = useState<Record<string, SourceState>>({});
  const inflight = useRef(new Set<string>());

  const load = useCallback((path: string) => {
    if (changed.current.has(path) || inflight.current.has(path)) return;
    inflight.current.add(path);
    setFetched((m) => ({ ...m, [path]: { status: "loading" } }));
    api.source(reviewId, path)
      .then((file) => setFetched((m) => ({ ...m, [path]: { status: "ok", file } })))
      .catch((e) => setFetched((m) => ({ ...m, [path]: { status: "error", error: String(e.message ?? e) } })))
      .finally(() => inflight.current.delete(path));
  }, [reviewId]);

  const reload = useCallback((path: string) => {
    setFetched((m) => {
      const { [path]: _, ...rest } = m;
      return rest;
    });
  }, []);

  const get = useCallback((path: string): SourceState | FileChange | undefined =>
    changed.current.get(path) ?? fetched[path], [fetched]);

  return useMemo(() => ({ get, load, reload }), [get, load, reload]);
}

export const isChange = (x: unknown): x is FileChange => !!x && typeof x === "object" && "before" in x && "after" in x;

/** Fetch `path` once it is shown (no-op for changed files and files already loaded). */
export function useEnsureSource(path: string | null, sources: ReturnType<typeof useSources>) {
  const state = path ? sources.get(path) : undefined;
  useEffect(() => {
    if (path && state === undefined) sources.load(path);
  }, [path, state, sources]);
  return state;
}
