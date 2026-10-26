import { type RefObject, useEffect, useLayoutEffect, useRef } from "react";

/** How far right `el` can be seen: the screen's edge, or the edge of a container around it that scrolls or clips,
 * whichever is nearest. An inline box has no width to clip with, and its overflow does not apply. */
function seenTo(el: HTMLElement): number {
  let edge = document.documentElement.clientWidth;
  for (let up = el.parentElement; up && up !== document.documentElement; up = up.parentElement) {
    if (!up.clientWidth || getComputedStyle(up).overflowX === "visible") continue;
    edge = Math.min(edge, up.getBoundingClientRect().left + up.clientLeft + up.clientWidth);
  }
  return edge;
}

/** A popup menu's behaviour (WAI-ARIA menu button): opening focuses its first enabled item; ArrowDown, ArrowUp, Home and
 * End move between items while focus is in the menu; Escape closes it and returns focus to its button; a press outside
 * the menu and its button closes it. A menu that would run past the right edge of what shows it (the screen, or a
 * container that scrolls or clips) hangs from its button's right edge instead; one that fits does not move. */
export function useMenu<M extends HTMLElement = HTMLElement>(open: boolean, close: () => void):
    { button: RefObject<HTMLButtonElement | null>; menu: RefObject<M | null> } {
  const button = useRef<HTMLButtonElement>(null), menu = useRef<M>(null);
  const shut = useRef(close);
  shut.current = close;
  useLayoutEffect(() => {                                  // before the first paint: it never shows at the wrong edge
    const el = menu.current;
    if (!open || !el || el.getBoundingClientRect().right <= seenTo(el)) return;
    el.style.left = "auto";                                // a page that scrolls would scroll sideways, one that clips would cut it off
    el.style.right = "0";
    return () => { el.style.left = ""; el.style.right = ""; };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const items = () => [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? [])];
    items()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); shut.current(); button.current?.focus(); return; }
      const all = items(), at = all.indexOf(document.activeElement as HTMLElement);
      if (at < 0) return;                                  // focus is elsewhere: the keys are not the menu's
      const to = { ArrowDown: (at + 1) % all.length, ArrowUp: (at - 1 + all.length) % all.length, Home: 0, End: all.length - 1 }[e.key];
      if (to !== undefined) { e.preventDefault(); all[to].focus(); }
    };
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !button.current?.contains(t)) shut.current();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", away);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", away); };
  }, [open]);
  return { button, menu };
}
