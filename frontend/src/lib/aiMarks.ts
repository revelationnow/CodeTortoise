import type { AiView } from "../api";
import type { Story } from "../board/types";

/** The hover on AI-written text (spec 2026-10-25-review-ui-redesign §1.2): the model only where the app knows it. */
export const aiTitle = (by?: string | null): string => (by ? `Written by AI · ${by}` : "Written by AI");

/** Who wrote a story's own title, purpose, questions and suggested checks: the strong model, when it formed the story. */
export const storyModel = (st: Pick<Story, "source">, view: Pick<AiView, "strong"> | null | undefined): string | null =>
  st.source === "tier1" ? view?.strong ?? null : null;
