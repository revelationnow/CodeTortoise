/** Size of a panel while its grip is dragged from `from` to `to` (pointer x, or y for a bottom grip): the panel grows
 * towards the side its grip faces — a left-edge grip grows when dragged left. Clamped to [min, max], rounded. */
export type Edge = "left" | "right" | "bottom";
export function dragSize(start: number, edge: Edge, from: number, to: number, min: number, max: number): number {
  const d = edge === "left" ? from - to : to - from;
  return Math.round(Math.max(min, Math.min(max, start + d)));
}
