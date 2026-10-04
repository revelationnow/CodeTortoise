import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Story, StorySet } from "../board/types";
import { countLine, sections } from "./stories";
import "./stories.css";

/** `code` spans for the backticked names in a story's title or summary. */
export function Ticks({ text }: { text: string }) {
  return <>{text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}</>;
}

interface Props {
  reviewId: number;
  stories: StorySet;
  /** The whole change's summary (the boards' "What's this change?"). */
  intent: string | null;
  head: (extra?: ReactNode) => ReactNode;
}

/** `/r/:id` (spec 2026-10-04-change-stories §2.4, §5): the review told as at most 15 stories. */
export default function StoryList({ reviewId, stories, intent, head }: Props) {
  const s = sections(stories);
  const entry = (st: Story, compact = false) => (
    <li key={st.id}>
      <Link to={`/r/${reviewId}/s/${st.id}`} className={`st-entry ${st.kind}${compact ? " compact" : ""}`}>
        <span className="st-top">
          <span className="st-id">{st.id}</span>
          {st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
          {st.kind === "mechanical" && <span className="st-skim">skim</span>}
          <span className="st-title">{st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></span>
        </span>
        {!compact && <span className="st-summary"><Ticks text={st.summary} /></span>}
        <span className="st-counts">{countLine(st)}</span>
      </Link>
    </li>
  );
  return (
    <main className="review stories bd">
      {head()}
      <div className="review-body st-list">
        <p className="st-lead"><Ticks text={stories.summary} /> <Link to={`/r/${reviewId}/board`} className="st-boards">Boards ›</Link></p>
        {intent && <p className="muted st-intent">{intent}</p>}
        {(s.behaviour.length > 0 || s.collapsed.length > 0) && (
          <section aria-label="Behaviour stories">
            <h2>What behaves differently</h2>
            <ol>{s.behaviour.map((st) => entry(st))}</ol>
            {s.collapsed.length > 0 && (
              <details className="st-collapsed">
                <summary>{s.collapsed.length} more behaviour stor{s.collapsed.length === 1 ? "y" : "ies"}</summary>
                <ol>{s.collapsed.map((st) => entry(st))}</ol>
              </details>
            )}
          </section>
        )}
        {s.other.length > 0 && <section aria-label="Other changes"><h2>Other changes</h2><ol>{s.other.map((st) => entry(st))}</ol></section>}
        {s.mechanical.length > 0 && (
          <section aria-label="Repeated edits"><h2>Repeated edits</h2><ol>{s.mechanical.map((st) => entry(st, true))}</ol></section>
        )}
        {s.tests.length > 0 && <section aria-label="Tests"><h2>Tests</h2><ol>{s.tests.map((st) => entry(st))}</ol></section>}
        {!stories.stories.length && <p className="muted">No changed functions. <Link to={`/r/${reviewId}/board`}>Open the board</Link></p>}
      </div>
    </main>
  );
}
