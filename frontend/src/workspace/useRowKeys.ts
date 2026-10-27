import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useWs } from "./context";
import { inPopup, typing } from "./keys";

/** Puts focus on row `n`'s toggle, the button that opens it. */
const focusRow = (n: number) => document.querySelector<HTMLElement>(`#flow-${n} .fl-toggle`)?.focus();

/** The Flows tab's row keys and where focus goes (spec 2026-10-25-review-ui-redesign §7.3). `cur` is the row J, K and F act on: the
 * last with focus in it, or clicked (`setCur`). `move(n)` puts focus on row n once its group has unfolded; `focusRow(n)` is for a
 * button that hands its focus back to its row. `order`: the rows as they read, group by group; `leftAt(n)`: the keys of row n's places
 * still open; `fine(keys)`: marks them. Enter is the focused row's own button. */
export default function useRowKeys({ order, busy, leftAt, fine }: {
  order: number[]; busy: boolean; leftAt: (n: number) => string[]; fine: (keys: string[]) => void;
}) {
  const ws = useWs();
  const [cur, setCur] = useState<number | null>(ws.addr.flow);
  const focusTo = useRef<number | null>(null);
  const move = (to: number | undefined) => {
    if (to === undefined) return;
    if (to === cur) focusRow(to);
    else { focusTo.current = to; setCur(to); }                               // focused once its group has unfolded
  };
  useEffect(() => {
    if (cur !== null && focusTo.current === cur) { focusTo.current = null; focusRow(cur); }
  }, [cur]);                                                                   // eslint-disable-line react-hooks/exhaustive-deps
  // J, K and F, read from a ref set in the render as the stepper's are: they wait while a mark is on its way, stay the stepper's
  // while a cause is open beside the page and are a menu's or a dialog's while one has focus. F acts once per press: a held key's
  // repeats would mark row after row.
  const onKey = useRef<(e: KeyboardEvent) => void>(() => {});
  onKey.current = (e) => {
    const stepper = !!ws.addr.open && "cause" in ws.addr.open;
    if (busy || stepper || e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || inPopup(e.target) || !order.length) return;
    const at = cur === null ? -1 : order.indexOf(cur);
    if (e.key === "j") { e.preventDefault(); move(order[at + 1]); }
    else if (e.key === "k") { e.preventDefault(); move(order[Math.max(at, 1) - 1]); }
    else if (e.key === "f" && !e.repeat && cur !== null && at >= 0) {
      e.preventDefault();
      const left = leftAt(cur), next = [...order.slice(at + 1), ...order.slice(0, at)].find((n) => leftAt(n).length > 0);
      if (left.length) fine(left);
      move(next ?? cur);                                                     // none left: stay on this row, not on a button its mark takes away
    }
  };
  useLayoutEffect(() => {                                                      // heard from the commit that shows the rows, not from the next paint
    const on = (e: KeyboardEvent) => onKey.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  return { cur, setCur, move, focusRow };
}
