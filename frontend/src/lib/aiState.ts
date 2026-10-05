import type { AiJob, AiView } from "../api";

/** Whether @tortoise can run for me on this review, and what to say about it in the @ menu. */
export function aiAvailability(v: AiView | null): { ok: boolean; detail: string } {
  if (!v || !v.llm) return { ok: false, detail: "no AI is configured for CodeTortoise" };
  if (v.used >= v.budget) return { ok: false, detail: `this review has used its ${v.budget} AI calls; the owner can raise it` };
  if (v.me_today >= v.me_limit) return { ok: false, detail: `you've used your ${v.me_limit} AI calls today` };
  return { ok: true, detail: `ask the AI about this thread — 1 AI call, reading code for up to ${v.per_mention} rounds · `
    + `${v.budget - v.used} left on this review, ${v.me_limit - v.me_today} left for you today` };
}

/** The cost on a ✦ button's hover. */
export const callTitle = (v: AiView): string => `1 AI call · ${Math.max(0, v.budget - v.used)} left on this review`;

/** The latest job for one item. */
export const jobFor = (v: AiView | null, kind: string, target: string): AiJob | undefined =>
  v?.jobs.filter((j) => j.kind === kind && j.target === target).at(-1);

/** Jobs that finished since `before`: running then, or not there yet (a fast job can finish between two loads). */
export function finished(before: AiView | null, after: AiView): AiJob[] {
  if (!before) return [];
  const was = new Map(before.jobs.map((j) => [j.id, j.status]));
  return after.jobs.filter((j) => j.status !== "running" && (was.get(j.id) ?? "running") === "running");
}
