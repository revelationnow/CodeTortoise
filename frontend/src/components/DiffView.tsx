import { Fragment, useState } from "react";
import type { Comment } from "../api";
import { diffRows } from "../lib/diffRows";
import Comments, { anchorMatches } from "./Comments";

interface Props {
  reviewId: number;
  depot: string;
  cl: number | null;
  before: string;
  after: string;
  comments: Comment[];
  onComments: () => void;
}

/** Unified diff with per-line comment threads (anchored to new line numbers, or old ones for deletions). */
export default function DiffView({ reviewId, depot, cl, before, after, comments, onComments }: Props) {
  const rows = diffRows(before, after);
  const [openAt, setOpenAt] = useState<string | null>(null);
  return (
    <table className="diff">
      <tbody>
        {rows.map((r, i) => {
          if (r.kind === "gap") return <tr key={i} className="gap"><td colSpan={4}>⋯ {r.text}</td></tr>;
          const side = r.newNo !== null ? "new" : "old";
          const line = r.newNo ?? r.oldNo;
          const anchor = { depot, cl, side, line };
          const key = `${side}:${line}`;
          const has = comments.some((c) => c.parent_id === null && anchorMatches(c, "line", anchor));
          return (
            <Fragment key={i}>
              <tr className={r.kind}>
                <td className="ln">{r.oldNo ?? ""}</td>
                <td className="ln">{r.newNo ?? ""}</td>
                <td className="add-comment"><button className="link" title="Comment on this line" onClick={() => setOpenAt(openAt === key ? null : key)}>+</button></td>
                <td className="code"><span className="sign">{r.kind === "add" ? "+" : r.kind === "del" ? "-" : " "}</span>{r.text}</td>
              </tr>
              {(has || openAt === key) && (
                <tr className="comment-row"><td colSpan={3} /><td>
                  <Comments reviewId={reviewId} comments={comments} kind="line" anchor={anchor} onChange={onComments} />
                </td></tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
