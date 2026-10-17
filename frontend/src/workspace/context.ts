import { createContext, useContext } from "react";
import type { Address, Item, Open, Place, Tab } from "./address";
import type { useSources } from "../board/useSources";
import type { OutlineView } from "../reading/causes";
import type { CheckKind } from "../reading/types";
import type { Screen } from "./media";
import type { ReviewData } from "./useReview";

/** Which columns are folded to strips (spec 2026-10-12 §3). */
export interface Folds { rail: boolean; check: boolean }

/** The workspace as every page and panel sees it: the review's data, the current address and ways to move. */
export interface Ws {
  base: string;
  data: ReviewData;
  addr: Address;
  screen: Screen;
  /** File text for the detail panel, fetched once per session. */
  sources: ReturnType<typeof useSources>;
  link: (a: Address) => string;
  /** Opening an item or the panel on something new pushes; switching flow, view or tab replaces (§2.4). */
  go: (a: Address, replace?: boolean) => void;
  /** An item as the reader left it this session (§2.4), for the rail and links between items. */
  item: (place: Place) => Address;
  /** The detail panel on `open` at the current place. */
  opened: (open: Open, tab?: Tab) => Address;
  /** The story the pointer (or focus) is on in the rail: maps light its nodes. */
  hover: string | null;
  setHover: (sid: string | null) => void;
  /** The side panel's tabs this visit, oldest first (spec 2026-10-12 §2.2); the address holds the active one. */
  tabs: Item[];
  closeTab: (o: Item) => void;
  /** The folds shown (both, while focused) and how the reader changes them; desktop only. */
  folds: Folds;
  setFold: (which: keyof Folds, folded: boolean) => void;
  /** Focus: the outline folded and the panel widened, until pressed again or the panel closes. */
  focus: boolean;
  toggleFocus: () => void;
  /** The outline's view, Stories or Checks, kept per browser (spec 2026-10-16-outline-and-causes §1.2). */
  outline: OutlineView;
  setOutline: (v: OutlineView) => void;
  /** The check kinds hidden from the outline, chips, counts and Next open check, kept per browser (§4.6). */
  hidden: ReadonlySet<CheckKind>;
  setHidden: (h: ReadonlySet<CheckKind>) => void;
  /** The CLs whose files are expanded on Index › CLs this visit (spec 2026-10-12 §5). */
  clsOpen: ReadonlySet<number>;
  setClsOpen: (cls: ReadonlySet<number>) => void;
}

export const WsContext = createContext<Ws | null>(null);

export function useWs(): Ws {
  const ws = useContext(WsContext);
  if (!ws) throw new Error("useWs outside the workspace");
  return ws;
}
