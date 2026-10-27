import type { HTMLAttributes, ReactNode } from "react";
import { aiTitle } from "../lib/aiMarks";

type Block = "p" | "li" | "div" | "span";

/** AI-written text (spec 2026-10-25-review-ui-redesign §1.1): a faint edge at its left, who wrote it on hover, and
 * "Written by AI." for screen readers; it renders as the element it replaces. `title` replaces the hover where the text
 * may be cut short and the hover has to carry the whole of it (as on `AiName`); `title={undefined}` keeps the hover.
 * `ai={false}` renders the plain element, so a caller passes its own source test. */
export default function AiText({ as: Tag = "p", ai = true, by, title, className, children, ...rest }:
  { as?: Block; ai?: boolean; by?: string | null; children: ReactNode } & HTMLAttributes<HTMLElement>) {
  if (!ai) return <Tag className={className} {...rest} title={title}>{children}</Tag>;
  return (
    <Tag className={className ? `ai-text ${className}` : "ai-text"} {...rest} title={title ?? aiTitle(by)}>
      <span className="vh">Written by AI. </span>{children}
    </Tag>
  );
}

/** An AI-written title or name shown as a heading (§1.1): no edge, the same hover; `title` replaces the hover where the
 * name may be cut short and the hover has to carry the whole of it. */
export function AiName({ ai = true, by, title, children }:
  { ai?: boolean; by?: string | null; title?: string; children: ReactNode }) {
  if (!ai) return <>{children}</>;
  return <span className="ai-name" title={title ?? aiTitle(by)}><span className="vh">Written by AI: </span>{children}</span>;
}
