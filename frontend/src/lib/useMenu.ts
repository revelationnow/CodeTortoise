import { type RefObject, useEffect, useLayoutEffect, useRef } from "react";

/** How far right `el` can be seen: the screen's edge, or the edge of a container around it that scrolls or clips,
 * whichever is nearest. An inline box has no width to clip with, and its overflow does not apply; a box fixed to the
 * screen is clipped by no container, whatever scrolls around its place in the tree. */
function seenTo(el: HTMLElement): number {
  let edge = document.documentElement.clientWidth;
  if (getComputedStyle(el).position === "fixed") return edge;
  for (let up = el.parentElement; up && up !== document.documentElement; up = up.parentElement) {
    if (!up.clientWidth || getComputedStyle(up).overflowX === "visible") continue;
    edge = Math.min(edge, up.getBoundingClientRect().left + up.clientLeft + up.clientWidth);
  }
  return edge;
}

/** The items a menu walks: plain, checkbox and radio items, whichever of them is not disabled. */
const ITEMS = '[role="menuitem"]:not([disabled]),[role="menuitemcheckbox"]:not([disabled]),[role="menuitemradio"]:not([disabled])';
/** The choice a radio menu stands on. A checkbox item is checked or not by itself: it says nothing about where to start. */
const CHOSEN = '[role="menuitemradio"][aria-checked="true"]';

/** A popup menu's behaviour (WAI-ARIA menu button): opening focuses its first enabled item, or the checked item of a radio
 * menu; ArrowDown, ArrowUp, Home and End move between items (plain, checkbox and radio) while focus is in the menu;
 * Escape closes it and returns focus to its button; a press outside the menu and its button closes it, even on a part of
 * the page that keeps its presses to itself; focus that leaves the menu (Tab, Shift+Tab back to its button, or anything
 * else) closes it and stays where it went. A menu that would run past the right edge of what shows it (the screen, or a
 * container that scrolls or clips) hangs from its button's right edge instead; one that fits does not move. */
export function useMenu<M extends HTMLElement = HTMLElement>(open: boolean, close: () => void):
    { button: RefObject<HTMLButtonElement | null>; menu: RefObject<M | null> } {
  const button = useRef<HTMLButtonElement>(null), menu = useRef<M>(null);
  const shut = useRef(close);
  useLayoutEffect(() => { shut.current = close; });        // the latest close, for the listeners below: set in a commit, not while rendering
  useLayoutEffect(() => {                                  // before the first paint: it never shows at the wrong edge
    const el = menu.current;
    if (!open || !el || el.getBoundingClientRect().right <= seenTo(el)) return;
    el.style.left = "auto";                                // a page that scrolls would scroll sideways, one that clips would cut it off
    el.style.right = "0";
    return () => { el.style.left = ""; el.style.right = ""; };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const items = () => [...(menu.current?.querySelectorAll<HTMLElement>(ITEMS) ?? [])];
    (items().find((el) => el.matches(CHOSEN)) ?? items()[0])?.focus();
    let tabbed = false;                                    // the last key was Tab: focus it moves onto the button leaves the menu
    const key = (e: KeyboardEvent) => {
      tabbed = e.key === "Tab";
      if (e.key === "Escape") { e.preventDefault(); shut.current(); button.current?.focus(); return; }
      const all = items(), at = all.indexOf(document.activeElement as HTMLElement);
      if (at < 0) return;                                  // focus is elsewhere: the keys are not the menu's
      const to = { ArrowDown: (at + 1) % all.length, ArrowUp: (at - 1 + all.length) % all.length, Home: 0, End: all.length - 1 }[e.key];
      if (to !== undefined) { e.preventDefault(); all[to].focus(); }
    };
    const away = (e: PointerEvent) => {
      tabbed = false;
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !button.current?.contains(t)) shut.current();
    };
    const left = (e: FocusEvent) => {                      // a press on the button moves focus there too: its click toggles the menu
      const t = e.target as Node;
      if (!menu.current?.contains(t) && (tabbed || !button.current?.contains(t))) shut.current();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", away, true);  // before the page's own handlers, which may stop it on its way
    document.addEventListener("focusin", left, true);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", away, true);
      document.removeEventListener("focusin", left, true);
    };
  }, [open]);
  return { button, menu };
}
