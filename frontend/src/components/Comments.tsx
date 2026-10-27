import { useRef, useState } from "react";
import { api, type AnchorKind, type Comment, errorText } from "../api";
import { useMe } from "../App";
import { useAi } from "../lib/ai";
import { aiAvailability } from "../lib/aiState";
import { insertMention, mentionOptions, mentionQuery, TORTOISE } from "../lib/mention";
import Logo from "./Logo";
import AiText from "./AiText";

export function anchorMatches(c: Comment, kind: AnchorKind, anchor: Record<string, unknown>): boolean {
  return c.anchor_kind === kind && Object.entries(anchor).every(([k, v]) => c.anchor[k] === v);
}

/** Fetches the comments again after an action; a promise that rejects says the list did not come back. */
type Reload = () => void | Promise<unknown>;

interface Props {
  reviewId: number;
  comments: Comment[];
  kind: AnchorKind;
  anchor: Record<string, unknown>;
  onChange: Reload;
  compact?: boolean;
  /** Which root comments belong here (default: same kind and anchor fields). */
  match?: (c: Comment) => boolean;
  autoFocus?: boolean;
}

/** What a refused action says, under the thread or composer it came from: the server's own words, else the action's sentence.
 * The next action clears it, so a success after a failure leaves nothing behind. An action the server took whose list then will not
 * reload is not a refused one: it says it is done and the list is not, in the same place. */
function useFailure(reload: Reload) {
  const [said, setSaid] = useState<string | null>(null);
  /** Runs `act`, the server call alone; settles to whether it landed (never rejects). When it did, the list reloads in the background:
   * the draft does not wait for that, and that failing says nothing against `act`. */
  const run = (act: () => Promise<unknown>, failed: string): Promise<boolean> => {
    setSaid(null);
    return act().then(() => {
      Promise.resolve().then(reload).catch(() => setSaid("Done, but the comments could not be reloaded."));
      return true;
    }, (e) => { setSaid(errorText(e, failed)); return false; });
  };
  return { said, run, clear: () => setSaid(null) };
}

/** A refusal's words; a role of alert, so a screen reader hears them where focus did not go. */
function Failure({ said }: { said: string | null }) {
  return said ? <div className="cm-err" role="alert">{said}</div> : null;
}

/** All threads for one anchor plus a composer. A comment, reply, Resolve, Reopen, delete or edit the server refuses says so beside
 * the thread or composer it came from, and a draft stays in its box. One it took, whose list will not reload, says that instead,
 * and the draft goes. */
export default function Comments({ reviewId, comments, kind, anchor, onChange, compact, match, autoFocus }: Props) {
  const roots = comments.filter((c) => c.parent_id === null && (match ? match(c) : anchorMatches(c, kind, anchor)));
  const [open, setOpen] = useState(!compact);
  const post = useFailure(onChange);
  if (!open && roots.length === 0)                  // a thread that arrives later (an Ask…) shows without a click
    return <button className="link small" onClick={() => setOpen(true)}>+ comment</button>;
  return (
    <div className="comments">
      {roots.map((root) => (
        <Thread key={root.id} root={root} replies={comments.filter((c) => c.parent_id === root.id)}
                reviewId={reviewId} onChange={onChange} />
      ))}
      <Composer onSubmit={(body) => post.run(() => api.addComment(reviewId, body, kind, anchor), "The comment could not be posted.")}
                autoFocus={autoFocus} placeholder={roots.length ? "Start another thread…" : "Leave a comment…"} />
      <Failure said={post.said} />
    </div>
  );
}

function Thread({ root, replies, reviewId, onChange }: { root: Comment; replies: Comment[]; reviewId: number; onChange: Reload }) {
  const act = useFailure(onChange);                  // a reply, Resolve or Reopen that was refused
  return (
    <div className={`thread ${root.resolved ? "resolved" : ""}`}>
      {[root, ...replies].map((c) => <CommentView key={c.id} c={c} onChange={onChange} />)}
      <div className="thread-actions">
        <Composer small placeholder="Reply…"
                  onSubmit={(body) => act.run(() => api.addComment(reviewId, body, root.anchor_kind, root.anchor, root.id),
                                              "The reply could not be posted.")} />
        <button className="link small" onClick={() => act.run(() => api.patchComment(root.id, { resolved: !root.resolved }),
                                                               `The thread could not be ${root.resolved ? "reopened" : "resolved"}.`)}>
          {root.resolved ? "Reopen" : "Resolve"}
        </button>
      </div>
      <Failure said={act.said} />
    </div>
  );
}

function CommentView({ c, onChange }: { c: Comment; onChange: Reload }) {
  const me = useMe();
  const usage = useAi();
  const act = useFailure(onChange);                  // a delete or an edit that was refused
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
        <span className="muted small">{c.created_at.replace("T", " ").slice(0, 16)}{c.edited_at ? " (edited)" : ""}</span>
        {mine && !editing && <button className="link small" onClick={() => setEditing(true)}>edit</button>}
        {(mine || me?.is_owner) && (
          <button className="link small" onClick={() => act.run(() => api.deleteComment(c.id), "The comment could not be deleted.")}>delete</button>
        )}
      </div>
      {editing ? (
        <div className="stack">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} />
          <div>
            <button onClick={() => act.run(() => api.patchComment(c.id, { body }).then(() => setEditing(false)),
                                           "The edit could not be saved.")}>Save</button>
            <button className="link" onClick={() => { act.clear(); setEditing(false); }}>Cancel</button>
          </div>
        </div>
      ) : meta?.pending ? (
        <div className="comment-body muted">thinking…{meta.round ? ` (round ${meta.round} of ${meta.of})` : ""}</div>
      ) : (
        // "I stopped…", "I couldn't answer…": the app wrote those, so they are not marked as the AI's words
        <AiText as="div" ai={ai && !meta?.error} className="comment-body">{c.body}</AiText>
      )}
      {ai && meta && meta.read.length > 0 && <div className="ai-read muted small">read: {meta.read.join(", ")}</div>}
      {ai && me?.is_owner && usage && /review has used its/.test(meta?.error ?? "") && (
        <button className="link small" onClick={() => usage.setUsageOpen(true)}>Raise budget</button>
      )}
      <Failure said={act.said} />
    </div>
  );
}

/** `onSubmit` settles to whether the text went: the draft stays in its box when it did not. */
function Composer({ onSubmit, placeholder, small, autoFocus }:
  { onSubmit: (body: string) => Promise<boolean>; placeholder: string; small?: boolean; autoFocus?: boolean }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form className={`composer ${small ? "small" : ""}`} onSubmit={(e) => {
      e.preventDefault();
      if (!body.trim()) return;
      setBusy(true);
      onSubmit(body.trim()).then((sent) => { if (sent) setBody(""); }).finally(() => setBusy(false));
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
              <b>@{o.name}</b>
              {o.detail && <span className="detail">{o.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
