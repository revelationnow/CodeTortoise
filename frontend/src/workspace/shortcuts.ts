import { keys, load, save } from "../board/prefs";

/** The single-key shortcuts (J, K and F on the Flows tab and in the stepper) are on unless the reader switched them off in the
 * ⋯ menu (WCAG 2.1.4). The switch is kept in this browser and read at each key press, so a change reaches the keys at once; only
 * a stored `false` turns them off, so storage that is blocked, empty or holds anything else leaves them on. */
export const shortcutsOn = () => load<unknown>(keys.shortcuts, true) !== false;
export const setShortcutsOn = (on: boolean) => save(keys.shortcuts, on);

/** What F says to a screen reader, in a live region, once its mark has landed (owner decision 2). */
export const MARKED_FINE = "Marked fine";
