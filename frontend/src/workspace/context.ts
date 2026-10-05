import { createContext, useContext } from "react";
import type { Address, Open, Place, Tab } from "./address";
import type { useSources } from "../board/useSources";
import type { Screen } from "./media";
import type { ReviewData } from "./useReview";

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
}

export const WsContext = createContext<Ws | null>(null);

export function useWs(): Ws {
  const ws = useContext(WsContext);
  if (!ws) throw new Error("useWs outside the workspace");
  return ws;
}
