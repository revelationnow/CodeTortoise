import { useRef, useState } from "react";
import { api, type AnchorKind, type Comment } from "../api";
import { useMe } from "../App";
import { useAi } from "../lib/ai";
import { aiAvailability } from "../lib/aiState";
import { insertMention, mentionOptions, mentionQuery, TORTOISE } from "../lib/mention";
import Logo from "./Logo";

export function anchorMatches(c: Comment, kind: AnchorKind, anchor: Record<string, unknown>): boolean {
  return c.anchor_kind === kind && Object.entries(anchor).every(([k, v]) => c.anchor[k] === v);
}

interface Props {
  reviewId: number;
  comments: Comment[];
  kind: AnchorKind;
  anchor: Record<string, unknown>;
  onChange: () => void;
  compact?: boolean;
  /** Which root comments belong here (default: same kind and anchor fields). */
  match?: (c: Comment) => boolean;
  autoFocus?: boolean;
}

/** All threads for one anchor plus a composer. */
export default function Comments({ reviewId, comments, kind, anchor, onChange, compact, match, autoFocus }: Props) {
  const roots = comments.filter((c) => c.parent_id === null && (match ? match(c) : anchorMatches(c, kind, anchor)));
  const [open, setOpen] = useState(!compact);
  if (!open && roots.length === 0)                  // a thread that arrives later (an Ask…) shows without a click
    return <button className="link small" onClick={() => setOpen(true)}>+ comment</button>;
  return (
    <div className="comments">
      {roots.map((root) => (
        <Thread key={root.id} root={root} replies={comments.filter((c) => c.parent_id === root.id)}
                reviewId={reviewId} onChange={onChange} />
      ))}
      <Composer onSubmit={(body) => api.addComment(reviewId, body, kind, anchor).then(onChange)} autoFocus={autoFocus}
                placeholder={roots.length ? "Start another thread…" : "Leave a comment…"} />
    </div>
  );
}

function Thread({ root, replies, reviewId, onChange }: { root: Comment; replies: Comment[]; reviewId: number; onChange: () => void }) {
  return (
    <div className={`thread ${root.resolved ? "resolved" : ""}`}>
      {[root, ...replies].map((c) => <CommentView key={c.id} c={c} onChange={onChange} />)}
      <div className="thread-actions">
        <Composer small placeholder="Reply…"
                  onSubmit={(body) => api.addComment(reviewId, body, root.anchor_kind, root.anchor, root.id).then(onChange)} />
        <button className="link small" onClick={() => api.patchComment(root.id, { resolved: !root.resolved }).then(onChange)}>
          {root.resolved ? "Reopen" : "Resolve"}
        </button>
      </div>
    </div>
  );
}

function CommentView({ c, onChange }: { c: Comment; onChange: () => void }) {
  const me = useMe();
  const usage = useAi();
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(c.body);
  const ai = c.author === TORTOISE;
  const mine = me?.user === c.author && !ai;
  const meta = c.ai_meta;
  return (
    <div className={`comment${ai ? " ai" : ""}${meta?.pending ? " pending" : ""}`}>
      <div className="comment-head">
        {ai && <Logo size={16} />}
        <strong>{c.author}</strong>
        {ai && <span className="ai-label">AI</span>}
        <span className="muted small">{c.created_at.replace("T", " ").slice(0, 16)}{c.edited_at ? " (edited)" : ""}</span>
        {mine && !editing && <button className="link small" onClick={() => setEditing(true)}>edit</button>}
        {(mine || me?.is_owner) && (
          <button className="link small" onClick={() => api.deleteComment(c.id).then(onChange)}>delete</button>
        )}
      </div>
      {editing ? (
        <div className="stack">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} />
          <div>
            <button onClick={() => api.patchComment(c.id, { body }).then(() => { setEditing(false); onChange(); })}>Save</button>
            <button className="link" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      ) : meta?.pending ? (
        <div className="comment-body muted">thinking…{meta.round ? ` (round ${meta.round} of ${meta.of})` : ""}</div>
      ) : (
        <div className="comment-body">{c.body}</div>
      )}
      {ai && meta && meta.read.length > 0 && <div className="ai-read muted small">read: {meta.read.join(", ")}</div>}
      {ai && me?.is_owner && usage && /review has used its/.test(meta?.error ?? "") && (
        <button className="link small" onClick={() => usage.setUsageOpen(true)}>Raise budget</button>
      )}
    </div>
  );
}

function Composer({ onSubmit, placeholder, small, autoFocus }:
  { onSubmit: (body: string) => Promise<unknown>; placeholder: string; small?: boolean; autoFocus?: boolean }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form className={`composer ${small ? "small" : ""}`} onSubmit={(e) => {
      e.preventDefault();
      if (!body.trim()) return;
      setBusy(true);
      onSubmit(body.trim()).then(() => setBody("")).finally(() => setBusy(false));
    }}>
      <MentionBox rows={small ? 1 : 2} value={body} placeholder={placeholder} autoFocus={autoFocus} onChange={setBody} />
      <button disabled={busy || !body.trim()}>{small ? "Reply" : "Comment"}</button>
    </form>
  );
}

/** A comment textarea with the @ menu (spec 2026-10-03 §6): @tortoise first, then the review's people. */
function MentionBox({ value, onChange, rows, placeholder, autoFocus }:
  { value: string; onChange: (v: string) => void; rows: number; placeholder: string; autoFocus?: boolean }) {
  const ai = useAi();
  const box = useRef<HTMLTextAreaElement>(null);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [closedAt, setClosedAt] = useState<number | null>(null);     // Esc: closed until another @ is typed
  const q = mentionQuery(value, caret);
  const options = q && q.start !== closedAt ? mentionOptions(q.query, ai?.people ?? [], aiAvailability(ai?.view ?? null)) : [];
  const open = options.length > 0;
  const at = Math.min(active, options.length - 1);
  const pick = (i: number) => {
    const o = options[i];
    if (!q || !o || o.disabled) { setClosedAt(q?.start ?? null); return; }
    const next = insertMention(value, q.start, caret, o.name);
    onChange(next.text);
    setCaret(next.caret);
    window.requestAnimationFrame(() => { box.current?.focus(); box.current?.setSelectionRange(next.caret, next.caret); });
  };
  const track = (el: HTMLTextAreaElement) => setCaret(el.selectionStart ?? el.value.length);
  return (
    <span className="mention-box">
      <textarea ref={box} rows={rows} value={value} placeholder={placeholder} autoFocus={autoFocus}
                aria-autocomplete="list" aria-expanded={open}
                onChange={(e) => {
                  onChange(e.target.value);
                  track(e.target);
                  setActive(0);
                  if (!mentionQuery(e.target.value, e.target.selectionStart ?? e.target.value.length)) setClosedAt(null);
                }}
                onSelect={(e) => track(e.currentTarget)}
                onKeyDown={(e) => {
                  if (!open) return;
                  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                    e.preventDefault();
                    setActive((at + (e.key === "ArrowDown" ? 1 : -1) + options.length) % options.length);
                  } else if (e.key === "Enter" || e.key === "Tab") {
                    e.preventDefault();
                    pick(at);
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    e.stopPropagation();
                    setClosedAt(q!.start);
                  }
                }} />
      {open && (
        <ul className="mention-menu" role="listbox" aria-label="Mention">
          {options.map((o, i) => (
            <li key={o.name} role="option" aria-selected={i === at} aria-disabled={o.disabled}
                className={`${i === at ? "on" : ""}${o.disabled ? " off" : ""}`}
                onMouseDown={(e) => e.preventDefault()} onClick={() => pick(i)}>
              {o.ai ? <Logo size={14} /> : <span className="who">@</span>}
              <b>@{o.name}</b>{o.ai && <span className="ai-label">AI</span>}
              {o.detail && <span className="detail">{o.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
