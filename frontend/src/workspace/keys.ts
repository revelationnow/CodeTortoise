/** Keys a page acts on are letters while the reader types (spec 2026-10-16-outline-and-causes Review Focus 5,
 * 2026-10-25-review-ui-redesign Review Focus 4): in a text input, a text area, a select or editable text — not on a
 * tick box, a radio or a button, where they still step. */
export const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || t.tagName === "TEXTAREA" || t.tagName === "SELECT"
    || (t instanceof HTMLInputElement && !["checkbox", "radio", "button", "submit", "reset"].includes(t.type)));
