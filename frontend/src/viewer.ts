/** Who the session is inside a review (spec 2026-10-31 §8): its sign-in on the review's server, and whether that sign-in owns
 * the review's workspace. Inside a review the UI asks this, never `/api/me`, whose sign-ins span servers: the same name on
 * another server is someone else. */
import { createContext, useContext } from "react";
import type { ReviewDetail, WorkspaceRef } from "./api";

export interface Viewer { user: string; is_owner: boolean; workspace: WorkspaceRef }

export const ViewerContext = createContext<Viewer | null>(null);
export const useViewer = () => useContext(ViewerContext);

/** The viewer a review's detail names; null until it has loaded. */
export function viewerOf(d: ReviewDetail | null): Viewer | null {
  return d ? { ...d.viewer, workspace: d.workspace } : null;
}
