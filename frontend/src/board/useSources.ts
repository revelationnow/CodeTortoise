import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ChangedFile, type FileChange } from "../api";
import type { SourceText } from "./types";

export type SourceState =
  | { status: "loading" }
  | { status: "ok"; file: SourceText }
  | { status: "error"; error: string };

/** Text of any file the board shows, fetched when shown and kept until the review's list of changed files changes (a
 * run): a changed file's change (`GET /file`: its text before and after, each CL's, who wrote each line), any other
 * file's text (`GET /source`, i.e. p4 print at the workspace's have revision). */
export function useSources(reviewId: number, files: ChangedFile[]) {
  const changed = useRef(new Set<string>());
  changed.current = new Set(files.map((f) => f.depot));
  const [fetched, setFetched] = useState<Record<string, SourceState | FileChange>>({});
  const inflight = useRef(new Set<string>());
  const list = useRef(0);                                  // what was asked for under an older list lands nowhere
  useEffect(() => {                                        // a new list: fetch again, as it says (changed or not)
    list.current += 1;
    inflight.current.clear();
    setFetched({});
  }, [files]);

  const load = useCallback((path: string) => {
    if (inflight.current.has(path)) return;
    inflight.current.add(path);
    const mine = list.current;
    const put = (v: SourceState | FileChange) => { if (mine === list.current) setFetched((m) => ({ ...m, [path]: v })); };
    setFetched((m) => ({ ...m, [path]: { status: "loading" } }));
    (changed.current.has(path) ? api.file(reviewId, path)
      : api.source(reviewId, path).then((file): SourceState => ({ status: "ok", file })))
      .then(put, (e) => put({ status: "error", error: String(e.message ?? e) }))
      .finally(() => { if (mine === list.current) inflight.current.delete(path); });
  }, [reviewId]);

  const reload = useCallback((path: string) => {
    setFetched((m) => {
      const { [path]: _, ...rest } = m;
      return rest;
    });
  }, []);

  const get = useCallback((path: string): SourceState | FileChange | undefined => fetched[path], [fetched]);

  return useMemo(() => ({ get, load, reload }), [get, load, reload]);
}

export const isChange = (x: unknown): x is FileChange => !!x && typeof x === "object" && "before" in x && "after" in x;

/** Fetch `path` once it is shown (no-op for a file already loaded or on its way). */
export function useEnsureSource(path: string | null, sources: ReturnType<typeof useSources>) {
  const state = path ? sources.get(path) : undefined;
  useEffect(() => {
    if (path && state === undefined) sources.load(path);
  }, [path, state, sources]);
  return state;
}
