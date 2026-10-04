import { type ReactNode, useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, type Comment } from "../../api";
import ThemeSwitch from "../../components/ThemeSwitch";
import { useAi } from "../../lib/ai";
import ChangePanel from "../ChangePanel";
import FileViewer from "../FileViewer";
import { keys, loadTab, type PhoneTab, save } from "../prefs";
import type { Action, BoardState } from "../reducer";
import type { AffectedDir } from "../sideEffects";
import type { Board } from "../types";
import type { useSources } from "../useSources";
import FlowReader from "./FlowReader";
import "./phone.css";

interface Props {
  reviewId: number;
  board: Board;
  state: BoardState;
  act: (a: Action) => void;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  sideEffects: AffectedDir[];
  head: (extra: ReactNode) => ReactNode;
  onOpenFile: (nodeId: string) => void;
  /** The Map tab's content: the board's canvas stage, built by Board. */
  map: ReactNode;
  /** Bumped by Board to show the Map (a cited function opens there). */
  showMap: number;
  /** A split review's clusters: the menu lists the overview and each cluster's board. */
  clusters?: { id: string; name: string }[];
  /** A story (spec 2026-10-04-change-stories §5): the first tab shows its steps, the second its graph. */
  steps?: ReactNode;
  /** The review's stories, for the menu. */
  stories?: { id: string; title: string }[];
  /** Bumped to show the Steps tab. */
  showSteps?: number;
}

const TABS: [PhoneTab, string, string][] = [["flows", "☰", "Flows"], ["map", "◎", "Map"], ["files", "▤", "Files"], ["summary", "✦", "Summary"]];
const STORY_TABS: Record<string, string> = { flows: "Steps", map: "Graph" };

/** The board on a phone (spec §13.2): compact header, one tab at a time, tab bar at the bottom. */
export default function PhoneBoard(p: Props) {
  const { reviewId, board, state, act } = p;
  const [tab, setTab] = useState<PhoneTab>(() => (p.steps ? "flows" : loadTab(reviewId) ?? (board.flows.length ? "flows" : "map")));
  const [menu, setMenu] = useState(false);
  const ai = useAi();
  const choose = (t: PhoneTab) => { setTab(t); if (!p.steps) save(keys.tab(reviewId), t); };
  const seen = useRef(state.viewer.reveal?.seq ?? 0);
  useEffect(() => {                                    // opening any file (⤢, picker, summary) shows it in Files
    const seq = state.viewer.reveal?.seq ?? 0;
    if (seq !== seen.current) { seen.current = seq; setTab("files"); }
  }, [state.viewer.reveal]);
  useEffect(() => { if (p.showMap) setTab("map"); }, [p.showMap]);
  useEffect(() => { if (p.showSteps) setTab("flows"); }, [p.showSteps]);
  const open = (path: string, line: number | null = null) => act({ t: "viewer.open", path, line, wide: false });

  return (
    <div className="bd phone">
      {p.head(<button className="ph-menu-btn" aria-label="Review menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button>)}
      {menu && (
        <nav className="ph-menu" onClick={() => setMenu(false)}>
          <NavLink to="/">All reviews</NavLink>
          {p.stories && <NavLink end to={`/r/${reviewId}`}>All stories</NavLink>}
          {p.stories?.map((s) => <NavLink key={s.id} to={`/r/${reviewId}/s/${s.id}`}>{s.id} · {s.title.replace(/`/g, "")}</NavLink>)}
          {p.stories && <NavLink to={`/r/${reviewId}/board`}>Boards</NavLink>}
          <NavLink to={`/r/${reviewId}/findings`}>Findings</NavLink>
          <NavLink to={`/r/${reviewId}/cls`}>CLs &amp; Swarm</NavLink>
          {p.clusters && <NavLink end to={`/r/${reviewId}/overview`}>Overview</NavLink>}
          {p.clusters?.map((c) => <NavLink key={c.id} to={`/r/${reviewId}/c/${c.id}`}>{c.id} · {c.name}</NavLink>)}
          {ai?.view?.llm && <button className="link" onClick={() => ai.setUsageOpen(true)}>AI usage</button>}
          <span onClick={(e) => e.stopPropagation()}><ThemeSwitch /></span>
          <button className="link" onClick={() => api.logout().then(() => window.location.assign("/login"))}>Log out</button>
        </nav>
      )}
      <div className={`ph-body ph-${tab}`}>
        {tab === "flows" && p.steps}
        {tab === "flows" && !p.steps && <FlowReader reviewId={reviewId} board={board} state={state} act={act} sources={p.sources}
                                        comments={p.comments} onComments={p.onComments} onOpenFile={p.onOpenFile} />}
        {tab === "map" && p.map}
        {tab === "files" && (state.viewer.files.length ? (
          <FileViewer reviewId={reviewId} viewer={state.viewer} dispatch={act} sources={p.sources} anns={board.impacts}
                      comments={p.comments} onComments={p.onComments} width={0} onWidth={() => {}} onWidthDone={() => {}} embedded />
        ) : (
          <div className="ph-pick">
            <h3>Files in this change</h3>
            {board.about.tree.flatMap((d) => d.files).map((f) => (
              <button key={f.path} onClick={() => open(f.path)}>📄 {f.name}<span>{f.path}</span></button>
            ))}
            {p.sideEffects.length > 0 && <h3>Files with side effects</h3>}
            {p.sideEffects.flatMap((d) => d.files).map((f) => (
              <button key={f.path} onClick={() => open(f.path, f.fns[0]?.line ?? null)}>⚠ {f.name}
                <span>{f.fns.map((x) => x.label).join(", ")}</span></button>
            ))}
          </div>
        ))}
        {tab === "summary" && (
          <ChangePanel open embedded onToggle={() => {}} reviewId={reviewId} comments={p.comments} onComments={p.onComments}
                       layers={board.layers} about={board.about} sideEffects={p.sideEffects} risk={p.risk}
                       openFiles={state.viewer.files} dispatch={act} wide={false} width={0} onWidth={() => {}} onWidthDone={() => {}} />
        )}
      </div>
      <nav className="ph-tabs" role="tablist">
        {TABS.map(([t, icon, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => choose(t)}>
            <i aria-hidden="true">{icon}</i>{(p.steps && STORY_TABS[t]) || label}
          </button>
        ))}
      </nav>
    </div>
  );
}
