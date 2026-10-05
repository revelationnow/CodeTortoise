/** Everything the workspace shows about one review (spec 2026-10-04-review-workspace §5: Review.tsx's data loading,
 * progress events and AI state, moved into a hook). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type AiJob, type Board, type Comment, type FileChange, type Finding, type Names, type Overview,
  type ReviewDetail, type StoryDetail, type StorySet } from "../api";
import { useAiState } from "../lib/ai";

const TERMINAL = new Set(["done", "degraded", "failed"]);
const missing = <T,>(fallback: T) => (e: unknown): T => {
  if (e instanceof ApiError && e.status === 404) return fallback;
  throw e;
};

export function useReview(id: number) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [board, setBoard] = useState<Board | null | undefined>(undefined);          // null: a split review, or none
  const [overview, setOverview] = useState<Overview | null | undefined>(undefined); // null: shown as one board
  const [stories, setStories] = useState<StorySet | null | undefined>(undefined);   // null: run before stories
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [names, setNames] = useState<Names>({});
  const [reload, setReload] = useState(0);                // story pages and cluster graphs fetch again: new results, AI text
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => setError(String((e as Error).message ?? e)), []);
  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch(fail), [id, fail]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadStories = useCallback(() => api.stories(id).then(setStories, (e) => setStories(missing(null)(e))), [id]);
  const loadNames = useCallback(() => api.names(id).then(setNames).catch(() => { /* names fall back to "a function" */ }), [id]);
  const loadBoard = useCallback(() => api.board(id).then(setBoard, (e) => setBoard(missing(null)(e))), [id]);
  const loadResults = useCallback(() => (setReload((k) => k + 1), Promise.all([
    api.overview(id).then((ov) => { setOverview(ov); setBoard(null); },
                          (e) => { setOverview(missing(null)(e)); return loadBoard(); }),
    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(), loadNames(),
  ]).catch(fail)), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, fail]);

  useEffect(() => { loadDetail(); }, [loadDetail]);
  const status = detail?.review.status;
  useEffect(() => {
    if (!status) return;
    if (TERMINAL.has(status)) { loadResults(); return; }
    const es = new EventSource(`/api/reviews/${id}/events`);
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setDetail((d) => (d ? { ...d, review: data.review, stages: data.stages } : d));
      if (TERMINAL.has(data.review.status)) { es.close(); loadDetail(); }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [id, status, loadResults, loadDetail]);

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
  }, [loadStories, loadNames, loadBoard, loadFindings, overview]);
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

  return { id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready, ai, story,
           loadDetail, loadComments, loadFindings };
}

export type ReviewData = ReturnType<typeof useReview>;
