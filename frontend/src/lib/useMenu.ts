import { type RefObject, useEffect, useRef } from "react";

/** A popup menu's behaviour (WAI-ARIA menu button): opening focuses its first enabled item; ArrowDown, ArrowUp, Home and
 * End move between items while focus is in the menu; Escape closes it and returns focus to its button; a press outside
 * the menu and its button closes it. */
export function useMenu<M extends HTMLElement = HTMLElement>(open: boolean, close: () => void):
    { button: RefObject<HTMLButtonElement | null>; menu: RefObject<M | null> } {
  const button = useRef<HTMLButtonElement>(null), menu = useRef<M>(null);
  const shut = useRef(close);
  shut.current = close;
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
