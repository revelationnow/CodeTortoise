/** Whether focus is inside `box`: what an Escape that closes a panel asks before it gives focus back to whatever opened the panel.
 * A panel closes on a press outside it, not when focus leaves it, so a reader who has Tabbed on is in the page with the panel still
 * open; Escape there only closes it, since pulling focus back would take it from where the reader is. */
export const holdsFocus = (box: Element | null | undefined): boolean => !!box?.contains(document.activeElement);
