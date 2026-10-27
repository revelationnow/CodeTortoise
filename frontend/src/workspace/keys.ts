/** `typing` is true while letters are the reader's own: in a text input, a text area, a select or editable text, where a page's
 * keys must not act (spec 2026-10-16-outline-and-causes Review Focus 5, 2026-10-25-review-ui-redesign Review Focus 4). On a tick
 * box, a radio or a button the keys act, by design: F must work while a tick box has focus. The ⋯ menu's Single-key shortcuts
 * switch (`shortcuts.ts`) turns them off for a reader who needs that (WCAG 2.1.4). */
export const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || t.tagName === "TEXTAREA" || t.tagName === "SELECT"
    || (t instanceof HTMLInputElement && !["checkbox", "radio", "button", "submit", "reset"].includes(t.type)));

/** Keys are the popup's while focus is inside a menu, a dialog or a list box: its items are buttons, which `typing` lets
 * through, and a page behind it must not act on the reader's keys. */
export const inPopup = (t: EventTarget | null) =>
  t instanceof Element && !!t.closest('[role="menu"],[role="dialog"],[role="listbox"]');

/** The key a press is, in lower case. Caps Lock and Shift make J, K and F arrive as capitals, and the shortcuts are the same keys;
 * Ctrl, Meta and Alt are for the caller to refuse. A press that carries no key (Chrome's autofill sends such events) is "". */
export const lowerKey = (e: KeyboardEvent) => (e.key ?? "").toLowerCase();
