import cytoscape, { type Core } from "cytoscape";
import elk from "cytoscape-elk";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Comment, Finding, Impact } from "../api";
import { flowElements, type GraphMode } from "../lib/graph";
import { SeverityBadge } from "./Badges";
import Comments from "./Comments";

cytoscape.use(elk);

const STYLE: cytoscape.StylesheetJson = [
  { selector: "node", style: { label: "data(label)", "font-size": 11, "text-valign": "center", "text-halign": "center",
    shape: "round-rectangle", width: "label", height: 26, padding: "8px", "background-color": "#e8e6e1",
    "border-width": 1, "border-color": "#8a8578", color: "#1d1b16" } },
  { selector: "node.field", style: { shape: "tag", "background-color": "#efe7d6", "font-style": "italic" } },
  { selector: "node.layer", style: { label: "data(label)", "text-valign": "top", "text-halign": "center", "font-size": 10,
    color: "#6b665b", "background-opacity": 0.35, "background-color": "#f4f2ee", "border-style": "dashed", "border-color": "#c9c4b8" } },
  { selector: "node.root", style: { "border-width": 3 } },
  { selector: "node.more", style: { "background-color": "#f4f2ee", "border-style": "dashed", color: "#6b665b", "font-style": "italic" } },
  { selector: "node.heuristic", style: { "border-style": "dotted" } },
  { selector: "node.st-changed", style: { "background-color": "#f6d98a", "border-color": "#a07a10" } },
  { selector: "node.st-added", style: { "background-color": "#b9e3b9", "border-color": "#2f7d32" } },
  { selector: "node.st-removed", style: { "background-color": "#f2b8b5", "border-color": "#b3261e" } },
  { selector: "node:selected", style: { "border-color": "#2451b8", "border-width": 3 } },
  { selector: "edge", style: { width: 1.5, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#8a8578",
    "target-arrow-color": "#8a8578", label: "data(label)", "font-size": 9, color: "#6b665b" } },
  { selector: "edge.conf-heuristic", style: { "line-style": "dotted" } },
  { selector: "edge.conf-may", style: { "line-style": "dotted", width: 1 } },
  { selector: "edge.data", style: { "line-style": "dashed", "line-color": "#9b6a2f", "target-arrow-color": "#9b6a2f" } },
  { selector: "edge.virtual", style: { "target-arrow-shape": "triangle-tee" } },
  { selector: "edge.st-added", style: { "line-color": "#2f7d32", "target-arrow-color": "#2f7d32", width: 2.5 } },
  { selector: "edge.st-removed", style: { "line-color": "#b3261e", "target-arrow-color": "#b3261e", width: 2.5 } },
];

interface Props {
  reviewId: number;
  impact: Impact;
  findings: Finding[];
  comments: Comment[];
  onComments: () => void;
  focus: string | null;
  onCite: (id: string) => void;
  layerName: (level: number | null) => string;
}

export default function CallFlows({ reviewId, impact, findings, comments, onComments, focus, onCite, layerName }: Props) {
  const [roots, setRoots] = useState<string[]>(impact.changed);
  const [mode, setMode] = useState<GraphMode>("diff");
  const [showData, setShowData] = useState(true);
  const [hideTests, setHideTests] = useState(true);
  const [maxCallers, setMaxCallers] = useState(6);
  const [depth, setDepth] = useState(2);
  const [selected, setSelected] = useState<string | null>(focus);
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);

  useEffect(() => {
    if (focus && impact.changed.includes(focus)) setRoots([focus]);
    if (focus) setSelected(focus);
  }, [focus, impact.changed]);

  const elements = useMemo(() => {
    const els = flowElements(impact, roots, mode, showData, { hideTests, maxCallers, maxCallees: maxCallers, depth });
    const layers = new Set<number>();
    for (const el of els) {
      const layer = el.data.layer as number | undefined;
      if (layer !== undefined && layer >= 0 && !el.data.source) {
        el.data.parent = `layer-${layer}`;
        layers.add(layer);
      }
    }
    const parents = [...layers].map((l) => ({ data: { id: `layer-${l}`, label: layerName(l) }, classes: "layer" }));
    return [...parents, ...els];
  }, [impact, roots, mode, showData, hideTests, maxCallers, depth, layerName]);

  useEffect(() => {
    if (!box.current) return;
    const inst = cytoscape({ container: box.current, elements, style: STYLE, wheelSensitivity: 0.3 });
    inst.layout({ name: "elk", elk: { algorithm: "layered", "elk.direction": "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN", "elk.layered.spacing.nodeNodeBetweenLayers": 40 } } as cytoscape.LayoutOptions).run();
    inst.on("tap", "node", (e) => { if (!e.target.hasClass("layer") && !e.target.hasClass("more")) setSelected(e.target.id()); });
    cy.current = inst;
    return () => inst.destroy();
  }, [elements]);

  useEffect(() => {
    if (!cy.current || !selected) return;
    cy.current.$(":selected").unselect();
    cy.current.$id(selected).select();
  }, [selected, elements]);

  const node = selected ? impact.nodes[selected] : null;
  const related = findings.filter((f) => selected && f.nodes.includes(selected));
  const incoming = impact.edges.filter((e) => e.dst === selected);
  const outgoing = impact.edges.filter((e) => e.src === selected);

  return (
    <div className="flows">
      <div className="toolbar">
        <label>Flow roots{" "}
          <select multiple value={roots} onChange={(e) => setRoots([...e.target.selectedOptions].map((o) => o.value))}>
            {impact.changed.map((id) => <option key={id} value={id}>{impact.nodes[id].label}</option>)}
          </select>
        </label>
        <div className="seg">
          {(["before", "after", "diff"] as const).map((m) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>{m}</button>
          ))}
        </div>
        <label><input type="checkbox" checked={showData} onChange={(e) => setShowData(e.target.checked)} /> field writes/reads</label>
        <label><input type="checkbox" checked={hideTests} onChange={(e) => setHideTests(e.target.checked)} /> hide test code</label>
        <label>depth{" "}
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label>fan-in/out per node{" "}
          <select value={maxCallers} onChange={(e) => setMaxCallers(Number(e.target.value))}>
            {[3, 6, 12, 25, 1000].map((n) => <option key={n} value={n}>{n === 1000 ? "all" : n}</option>)}
          </select>
        </label>
        <span className="legend small muted">solid = call (clang) · dotted = heuristic/may · dashed = field data · ⊣ virtual</span>
      </div>
      <div className="flows-body">
        <div ref={box} className="graph" data-testid="flow-graph" />
        <aside className="side">
          {!node ? <p className="muted">Select a node.</p> : (
            <>
              <h3>{node.label}</h3>
              <p className="small muted">{node.kind} · {node.status} · {layerName(node.layer)} · {node.confidence}</p>
              {node.file && <p className="mono small">{node.file}{node.line ? `:${node.line}` : ""}</p>}
              {related.length > 0 && (
                <>
                  <h4>Findings</h4>
                  <ul>{related.map((f) => (
                    <li key={f.id}><SeverityBadge severity={f.severity} /> <button className="link" onClick={() => onCite(f.id)}>{f.id}: {f.title}</button></li>
                  ))}</ul>
                </>
              )}
              <h4>Callers / users ({incoming.length})</h4>
              <ul className="small">{incoming.slice(0, 30).map((e) => (
                <li key={e.id}><button className="link" onClick={() => setSelected(e.src)}>{impact.nodes[e.src].label}</button> <span className="muted">{e.kind} · {e.status} · {e.confidence}</span></li>
              ))}</ul>
              <h4>Calls / touches ({outgoing.length})</h4>
              <ul className="small">{outgoing.slice(0, 30).map((e) => (
                <li key={e.id}><button className="link" onClick={() => setSelected(e.dst)}>{impact.nodes[e.dst].label}</button> <span className="muted">{e.kind} · {e.status} · {e.confidence}</span></li>
              ))}</ul>
              <Comments reviewId={reviewId} comments={comments} kind="function" anchor={{ key: node.key }} onChange={onComments} compact />
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
