import { useState } from "react";
import { api, type AnchorKind, type Comment } from "../api";
import { useMe } from "../App";

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
}

/** All threads for one anchor plus a composer. */
export default function Comments({ reviewId, comments, kind, anchor, onChange, compact }: Props) {
  const roots = comments.filter((c) => c.parent_id === null && anchorMatches(c, kind, anchor));
  const [open, setOpen] = useState(!compact || roots.length > 0);
  if (!open)
    return <button className="link small" onClick={() => setOpen(true)}>+ comment</button>;
  return (
    <div className="comments">
      {roots.map((root) => (
        <Thread key={root.id} root={root} replies={comments.filter((c) => c.parent_id === root.id)}
                reviewId={reviewId} onChange={onChange} />
      ))}
      <Composer onSubmit={(body) => api.addComment(reviewId, body, kind, anchor).then(onChange)}
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
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(c.body);
  const mine = me?.user === c.author;
  return (
    <div className="comment">
      <div className="comment-head">
        <strong>{c.author}</strong>
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
      ) : (
        <div className="comment-body">{c.body}</div>
      )}
    </div>
  );
}

function Composer({ onSubmit, placeholder, small }: { onSubmit: (body: string) => Promise<unknown>; placeholder: string; small?: boolean }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form className={`composer ${small ? "small" : ""}`} onSubmit={(e) => {
      e.preventDefault();
      if (!body.trim()) return;
      setBusy(true);
      onSubmit(body.trim()).then(() => setBody("")).finally(() => setBusy(false));
    }}>
      <textarea rows={small ? 1 : 2} value={body} placeholder={placeholder} onChange={(e) => setBody(e.target.value)} />
      <button disabled={busy || !body.trim()}>{small ? "Reply" : "Comment"}</button>
    </form>
  );
}
