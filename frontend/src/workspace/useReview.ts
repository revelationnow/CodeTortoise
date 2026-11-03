/** Everything the workspace shows about one review (spec 2026-10-04-review-workspace §5: Review.tsx's data loading,
 * progress events and AI state, moved into a hook). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type AiJob, type Board, type ChangedFile, type Comment, errorText, type Finding, type Names, type Overview,
  type Reading, type ReviewDetail, type StoryDetail, type StorySet } from "../api";
import { useAiState } from "../lib/ai";
import type { ReadTicks } from "../reading/plan";

const TERMINAL = new Set(["done", "degraded", "failed"]);
const NONE: Finding[] = [];
const missing = <T,>(fallback: T) => (e: unknown): T => {
  if (e instanceof ApiError && e.status === 404) return fallback;
  throw e;
};
/** Whether a review's design stage waits or runs: saving a design context re-runs it alone (spec 2026-11-02 §8). */
const designBusy = (d: ReviewDetail | null | undefined) =>
  !!d?.stages.some((s) => s.name === "design" && (s.status === "pending" || s.status === "running"));

export function useReview(id: number) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [board, setBoard] = useState<Board | null | undefined>(undefined);          // null: a split review, or none
  const [overview, setOverview] = useState<Overview | null | undefined>(undefined); // null: shown as one board
  const [stories, setStories] = useState<StorySet | null | undefined>(undefined);   // null: run before stories
  const [findings, setFindings] = useState<Finding[] | undefined>(undefined);       // undefined: on its way
  const [files, setFiles] = useState<ChangedFile[] | undefined>(undefined);         // undefined: on its way, again at a run's end
  const [comments, setComments] = useState<Comment[]>([]);
  const [names, setNames] = useState<Names>({});
  const [reading, setReading] = useState<Reading | null | undefined>(undefined);   // null: run before the reading existed
  const [ticks, setTicks] = useState<ReadTicks | null>(null);                          // the reader's own (phase 2 §6)
  const [reload, setReload] = useState(0);                // story pages and cluster graphs fetch again: new results, AI text
  const [error, setError] = useState<string | null>(null);
  const [signIn, setSignIn] = useState<string | null>(null);   // the server to sign in to before this review opens (spec 2026-10-31 §9)
  const [stream, setStream] = useState(0);                // the progress stream opened again: it dropped while the run went on

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401 && e.server) setSignIn(e.server);   // a review on a server the session isn't signed in to
    else setError(errorText(e, "The review could not be loaded."));
  }, []);
  const loadDetail = useCallback(() => api.review(id).then((d) => { setSignIn(null); setDetail(d); return d; }).catch(fail), [id, fail]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadStories = useCallback(() => api.stories(id).then(setStories, (e) => setStories(missing(null)(e))), [id]);
  const loadNames = useCallback(() => api.names(id).then(setNames).catch(() => { /* names fall back to "a function" */ }), [id]);
  const loadReading = useCallback(() => api.reading(id).then(setReading, (e) => setReading(missing(null)(e))), [id]);
  /** The reader's ticks; a failure reaches the caller, and the last ticks stay on screen. */
  const loadTicks = useCallback(() => api.ticks(id).then(setTicks), [id]);
  /** Tick or untick a story or check for the reader, then show what the server holds. */
  const tick = useCallback((kind: "story" | "check", key: string, on: boolean) => api.tick(id, kind, key, on).then(loadTicks), [id, loadTicks]);
  const loadBoard = useCallback(() => api.board(id).then(setBoard, (e) => setBoard(missing(null)(e))), [id]);
  // asked in this order: what the layout and a page wait on first (the reading, the stories), then the list of changed
  // files a panel waits on; the names, the slowest, last. The old list is dropped at once, and a finished run's texts with it.
  const loadResults = useCallback(() => (setReload((k) => k + 1), setFiles(undefined), Promise.all([
    loadReading(), loadStories(), api.files(id).then(setFiles),
    loadTicks().catch(() => { /* no reading plan until the ticks load */ }),
    api.overview(id).then((ov) => { setOverview(ov); setBoard(null); },
                          (e) => { setOverview(missing(null)(e)); return loadBoard(); }),
    loadFindings(), loadComments(), loadNames(),
  ]).catch(fail)), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, loadReading, loadTicks, fail]);

  useEffect(() => { loadDetail(); }, [loadDetail]);
  const status = detail?.review.status;
  useEffect(() => {
    if (!status) return;
    if (TERMINAL.has(status)) { loadResults(); return; }
    const es = new EventSource(`/api/reviews/${id}/events`);
    let later: ReturnType<typeof setTimeout> | undefined;
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setDetail((d) => (d ? { ...d, review: data.review, stages: data.stages } : d));
      if (TERMINAL.has(data.review.status)) { es.close(); loadDetail(); }
    };
    // the stream ended before the run did (a dropped connection, a restarted server): after a moment the review loads
    // again; a new status follows it on a new stream, and the same status opens this stream again
    es.onerror = () => {
      es.close();
      later = setTimeout(() => loadDetail().then((d) => { if (d?.review.status === status) setStream((k) => k + 1); }), 1000);
    };
    return () => { es.close(); clearTimeout(later); };
  }, [id, status, stream, loadResults, loadDetail]);

  // a design context saved re-runs the design stage alone (spec 2026-11-02 §8): the review stays done, so no stream
  // tells of it. The stage is polled while it waits or runs — from the save on (`awaitDesign`), as it may be done before
  // the first look — and the reading (its design and its lead) loads again once it is done.
  const [designWait, setDesignWait] = useState(false);
  const designing = designWait || designBusy(detail);
  const awaitDesign = useCallback(() => setDesignWait(true), []);
  useEffect(() => {
    if (!designing || !status || !TERMINAL.has(status)) return;
    const t = setInterval(() => { loadDetail().then((d) => { if (d && !designBusy(d)) setDesignWait(false); }); }, 1500);
    return () => clearInterval(t);
  }, [designing, status, loadDetail]);
  const wasDesigning = useRef(false);
  useEffect(() => {
    if (wasDesigning.current && !designing) loadReading();
    wasDesigning.current = designing;
  }, [designing, loadReading]);

  const ready = !!status && TERMINAL.has(status);
  const people = useMemo(() => [...new Set([detail?.review.created_by ?? "", ...comments.map((c) => c.author)])].filter(Boolean),
                         [detail, comments]);
  const onAiDone = useCallback((jobs: AiJob[]) => {      // an explanation finished: show it
    if (jobs.some((j) => j.kind === "flow" || j.kind === "story")) {
      setReload((k) => k + 1);
      loadStories();
      loadNames();
      if (overview === null) loadBoard();
    }
    if (jobs.some((j) => j.kind === "finding")) { loadFindings(); loadNames(); }
    if (jobs.some((j) => j.kind === "design")) loadReading();         // a part of the design overview was rewritten
  }, [loadStories, loadNames, loadBoard, loadFindings, loadReading, overview]);
  const cache = useRef(new Map<string, Promise<StoryDetail>>());
  /** A story's page data, fetched once and again after AI text changes it. */
  const story = useCallback((sid: string) => {
    let p = cache.current.get(`${reload}:${sid}`);
    if (!p) {
      p = api.story(id, sid);
      p.catch(() => cache.current.delete(`${reload}:${sid}`));
      cache.current.set(`${reload}:${sid}`, p);
    }
    return p;
  }, [id, reload]);
  const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
  const about = (board ?? overview)?.about ?? null;

  // the findings so far ([] until they come), and whether they came: a finding's page waits for them
  return useMemo(() => ({ id, detail, board, overview, stories, findings: findings ?? NONE, findingsLoaded: findings !== undefined,
                         files, comments, names, reading, ticks, about, reload, error, signIn,
                         ready, designing, awaitDesign, ai, story, loadDetail, loadComments, loadFindings, loadReading, loadTicks, tick }),
                 [id, detail, board, overview, stories, findings, files, comments, names, reading, ticks, about, reload, error, signIn, ready,
                  designing, awaitDesign, ai, story, loadDetail, loadComments, loadFindings, loadReading, loadTicks, tick]);
}

export type ReviewData = ReturnType<typeof useReview>;
