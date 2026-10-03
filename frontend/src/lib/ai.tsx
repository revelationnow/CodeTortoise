import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, ApiError, type AiJob, type AiKind, type AiView } from "../api";
import { finished } from "./aiState";

/** The review's AI state for every ✦ button, the @ menu, tortoise replies and the AI pill (spec 2026-10-03 §6). */
export interface Ai {
  reviewId: number;
  view: AiView | null;
  people: string[];
  /** Errors from asking (a refusal, a missing item), by "kind:target"; refused: the review or a person is over a limit. */
  asked: Record<string, { error: string; refused: boolean }>;
  explain: (kind: AiKind, target: string) => Promise<void>;
  refresh: () => Promise<void>;
  usageOpen: boolean;
  setUsageOpen: (open: boolean) => void;
}

const AiContext = createContext<Ai | null>(null);
export const AiProvider = AiContext.Provider;
export const useAi = () => useContext(AiContext);

const POLL_MS = 1500;

/** Loads /ai, and while a job runs or a tortoise reply is pending polls it (and the comments) until they finish. */
export function useAiState(reviewId: number, enabled: boolean, people: string[], pendingReplies: boolean,
                           onFinished: (jobs: AiJob[]) => void, onComments: () => void): Ai {
  const [view, setView] = useState<AiView | null>(null);
  const [asked, setAsked] = useState<Ai["asked"]>({});
  const [usageOpen, setUsageOpen] = useState(false);
  const last = useRef<AiView | null>(null);
  const done = useRef(onFinished);
  done.current = onFinished;
  const refresh = useCallback(() => api.ai(reviewId).then((v) => {
    const over = finished(last.current, v);
    last.current = v;
    setView(v);
    if (over.length) done.current(over);
  }).catch(() => { /* the pill and buttons stay as they were */ }), [reviewId]);
  useEffect(() => { if (enabled) refresh(); }, [enabled, refresh]);
  const running = !!view?.jobs.some((j) => j.status === "running");
  useEffect(() => {
    if (!enabled || !(running || pendingReplies)) return;
    const t = window.setInterval(() => { refresh(); if (pendingReplies) onComments(); }, POLL_MS);
    return () => window.clearInterval(t);
  }, [enabled, running, pendingReplies, refresh, onComments]);
  const explain = useCallback(async (kind: AiKind, target: string) => {
    const key = `${kind}:${target}`;
    setAsked(({ [key]: _, ...rest }) => rest);
    try {
      await api.explain(reviewId, kind, target);
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      setAsked((a) => ({ ...a, [key]: { error, refused: e instanceof ApiError && e.status === 429 } }));
    }
    await refresh();
  }, [reviewId, refresh]);
  return { reviewId, view, people, asked, explain, refresh, usageOpen, setUsageOpen };
}
