import { useCallback, useEffect, useRef, useState } from "react";

/** How long words stay in a live region: a screen reader's top-down read of the page, long after, would meet them as news. */
const SAID_FOR = 5000;

/** The words of a polite live region, which the caller renders (a visually hidden `aria-live="polite"` div holding `said`).
 * `say(landed, words)` is for a change that may fail: it empties the region now, so the same words are announced again, and
 * puts `words` there once `landed` settles to true (a change that did not land says nothing). The words clear themselves
 * `SAID_FOR` ms after they were set; that timer is dropped by the next `say` and when the caller goes. */
export default function useSaid(): { said: string; say: (landed: Promise<boolean>, words: string) => void } {
  const [said, setSaid] = useState("");
  const turn = useRef(0), timer = useRef<number | undefined>(undefined);
  useEffect(() => () => { turn.current++; window.clearTimeout(timer.current); }, []);
  const say = useCallback((landed: Promise<boolean>, words: string) => {
    const mine = ++turn.current;
    window.clearTimeout(timer.current);
    setSaid("");
    landed.then((ok) => {
      if (!ok || mine !== turn.current) return;                                // a later `say`, or a caller that has gone, has taken over
      setSaid(words);
      timer.current = window.setTimeout(() => setSaid(""), SAID_FOR);
    }).catch(() => {});                                                        // `landed` never rejects; one that did would say nothing
  }, []);
  return { said, say };
}
