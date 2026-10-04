import { type ReactNode, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Comment, type FileChange, type Finding } from "../api";
import Board, { usePhone } from "../board/Board";
import { useExpansion } from "../board/ClusterBoard";
import type { StoryDetail, StorySet } from "../board/types";
import { useSources } from "../board/useSources";
import Explain from "../components/Explain";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import { Ticks } from "./StoryList";
import StorySteps from "./StorySteps";
import { countLine, stepStory, wholeGraph } from "./stories";
import "./stories.css";

interface Props {
  reviewId: number;
  stories: StorySet;
  sid: string;
  files: FileChange[];
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  head: (extra?: ReactNode) => ReactNode;
  findings: Finding[];
  onCite: (id: string) => void;
  /** Bumped when an AI explanation finished: the story is fetched again. */
  reload: number;
}

/** `/r/:id/s/:sid` (spec 2026-10-04-change-stories §3, §5): one story, its Steps first and its graph on a tab;
 * ‹ › to the neighbouring stories. */
export default function StoryPage({ reviewId, stories, sid, files, comments, onComments, risk, head, findings, onCite,
  reload }: Props) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const prefKey = `${reviewId}.${sid}`;
  const { expand, expansion } = useExpansion(prefKey);
  const [detail, setDetail] = useState<StoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [moreTick, setMoreTick] = useState(0);
  const phone = usePhone();
  const sources = useSources(reviewId, files);
  useEffect(() => {
    let live = true;
    api.story(reviewId, sid, expand).then((d) => { if (live) { setDetail(d); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [reviewId, sid, expand, reload]);
  const focus = params.get("node");
  useEffect(() => {                                         // a node this story doesn't hold: open the story that does
    if (!detail || !focus || detail.board.nodes.some((n) => n.id === focus)) return;
    const there = stories.node_story[focus];
    if (there && there !== sid) navigate(`/r/${reviewId}/s/${there}?node=${encodeURIComponent(focus)}`, { replace: true });
  }, [detail, focus, stories, reviewId, sid, navigate]);

  const st = detail?.story ?? stories.stories.find((s) => s.id === sid);
  const hasGraph = !!detail?.graph && (st?.kind === "behaviour" || st?.kind === "other");
  const tab = hasGraph && params.get("tab") === "graph" ? "graph" : "steps";
  const setTab = (t: "steps" | "graph") => {
    const q = new URLSearchParams(params);
    if (t === "graph") q.set("tab", "graph"); else q.delete("tab");
    setParams(q, { replace: true });
  };
  const go = (by: number) => navigate(`/r/${reviewId}/s/${stepStory(stories, sid, by)}`);
  const at = stories.stories.findIndex((s) => s.id === sid);
  const nav = (
    <span className="bd-crumb st-crumb">
      <Link to={`/r/${reviewId}`}>Stories</Link><span className="sep"> › </span><b>{sid}</b>
      <button className="bd-ibtn" aria-label="Previous story" onClick={() => go(-1)}>‹</button>
      <span className="pos">{at + 1} of {stories.stories.length}</span>
      <button className="bd-ibtn" aria-label="Next story" onClick={() => go(1)}>›</button>
      {hasGraph && !phone && (
        <span className="bd-seg" role="tablist">
          <button role="tab" aria-selected={tab === "steps"} className={`bd-ibtn${tab === "steps" ? " on" : ""}`} onClick={() => setTab("steps")}>Steps</button>
          <button role="tab" aria-selected={tab === "graph"} className={`bd-ibtn${tab === "graph" ? " on" : ""}`} onClick={() => setTab("graph")}>Graph</button>
        </span>
      )}
      {st && st.kind !== "mechanical" && <Link className="st-whole" to={wholeGraph(reviewId, st, detail?.board.flows[0]?.cause)}>Whole graph ›</Link>}
    </span>
  );
  if (error)
    return (
      <main className="review stories bd">{head(nav)}
        <div className="review-body"><div className="banner warn">{error} <Link to={`/r/${reviewId}`}>All stories</Link>
          {expansion.onReset && <> <button className="link" onClick={expansion.onReset}>Reset</button></>}</div></div>
      </main>
    );
  if (!detail || !st) return <main className="page muted">Loading {sid}…</main>;
  const header = (
    <div className="st-head">
      <h2>{st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
        {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
      <p><Ticks text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} />}</p>
      <p className="st-counts">{countLine(st)}</p>
    </div>
  );
  const steps = <StorySteps reviewId={reviewId} detail={detail} sources={sources} comments={comments} onComments={onComments}
                            findings={findings} onCite={onCite} focus={focus} />;
  if (hasGraph && detail.graph && (phone || tab === "graph"))
    return (
      <main className="review board">
        <Board key={sid} reviewId={reviewId} board={detail.graph} files={files} comments={comments} onComments={onComments}
               risk={risk} focus={tab === "graph" ? focus : null} head={head} expansion={expansion}
               story={{ prefKey, nav, steps: <div className="st-phone">{header}{steps}</div>, showSteps: moreTick,
                        onMore: () => { setMoreTick((k) => k + 1); setTab("steps"); },
                        list: stories.stories.map((s) => ({ id: s.id, title: s.title })) }} />
      </main>
    );
  return (
    <main className="review stories bd">
      {head(nav)}
      <div className="review-body st-page">
        {header}
        {st.kind === "mechanical" ? <MechanicalStory reviewId={reviewId} detail={detail} />
          : st.kind === "tests" ? <TestsStory reviewId={reviewId} detail={detail} sources={sources} comments={comments} onComments={onComments} />
          : steps}
      </div>
    </main>
  );
}
