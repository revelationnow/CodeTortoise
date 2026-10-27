import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ChangedFile, errorText, type FileChange } from "../api";
import type { SourceText } from "./types";

export type SourceState =
  | { status: "loading" }
  | { status: "ok"; file: SourceText }
  | { status: "error"; error: string };

/** Text of any file the board shows, fetched when shown and kept until the review's list of changed files changes (a
 * run): a changed file's change (`GET /file`: its text before and after, each CL's, who wrote each line), any other
 * file's text (`GET /source`, i.e. p4 print at the workspace's have revision). Which of the two waits for the list
 * (`files` undefined: on its way); when it comes, each file shown is asked for. */
export function useSources(reviewId: number, files: ChangedFile[] | undefined) {
  const changed = useRef<Set<string> | null>(null);
  changed.current = files ? new Set(files.map((f) => f.depot)) : null;
  const [fetched, setFetched] = useState<Record<string, SourceState | FileChange>>({});
  const inflight = useRef(new Set<string>());
  const list = useRef(0);                                  // what was asked for under an older list lands nowhere
  useEffect(() => {                                        // a new list (or none yet): fetch again, as it says
    list.current += 1;
    inflight.current.clear();
    setFetched({});
  }, [files]);

  const load = useCallback((path: string) => {
    if (!changed.current || inflight.current.has(path)) return;   // asked again once the list is in (the reset above)
    inflight.current.add(path);
    const mine = list.current;
    const put = (v: SourceState | FileChange) => { if (mine === list.current) setFetched((m) => ({ ...m, [path]: v })); };
    setFetched((m) => ({ ...m, [path]: { status: "loading" } }));
    (changed.current.has(path) ? api.file(reviewId, path)
      : api.source(reviewId, path).then((file): SourceState => ({ status: "ok", file })))
      .then(put, (e) => put({ status: "error", error: errorText(e, "The file could not be loaded.") }))
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
