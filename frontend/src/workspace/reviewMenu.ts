/** The review header's ⋯ menu (spec 2026-10-25-review-ui-redesign §2.2): what moved out of the header row. */
export type MenuId = "drift" | "notes" | "ai" | "help" | "keys" | "rerun" | "fresh";
/** `checked` is set on a checkbox item (the single-key shortcuts switch), whether it is on; a plain item leaves it out. */
export interface MenuItem { id: MenuId; label: string; checked?: boolean }
export interface MenuState {
  drift: number;                                  // workspace drift lines (warnings)
  notes: { failed: number; degraded: number };    // stages that failed or degraded
  ai: { used: number; budget: number } | null;    // null: no AI configured
  reading: boolean;                               // the review has a reading
  keys: boolean;                                  // the single-key shortcuts are on
  owner: boolean;
  ready: boolean;
  strong: boolean;                                // a strong model is configured
}

/** The items, each only when it applies, in the spec's order. */
export function menuItems(m: MenuState): MenuItem[] {
  const out: MenuItem[] = [], notes = m.notes.failed + m.notes.degraded;
  if (m.drift > 0) out.push({ id: "drift", label: `Workspace drift · ${m.drift}` });
  if (notes > 0) out.push({ id: "notes", label: `Stage notes · ${notes}` });
  if (m.ai) out.push({ id: "ai", label: `AI calls used · ${m.ai.used} of ${m.ai.budget}` });
  if (m.reading) {
    out.push({ id: "help", label: "How to read this page" });
    out.push({ id: "keys", label: "Single-key shortcuts", checked: m.keys });
  }
  if (m.owner && m.ready) out.push({ id: "rerun", label: "Re-run" });
  if (m.owner && m.ready && m.strong) out.push({ id: "fresh", label: "Re-run stories, fresh" });
  return out;
}

/** What the amber dot on ⋯ is for, said in the button's name; null when nothing needs attention (a degraded stage
 * alone does not light it). */
export function menuAttention(m: MenuState): string | null {
  const why: string[] = [];
  if (m.drift > 0) why.push("workspace drift");
  if (m.notes.failed > 0) why.push("a stage failed");
  return why.length ? why.join(", ") : null;
}
