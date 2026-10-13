/** A folded column (spec 2026-10-12-story-account-and-panels §3): a 28px strip with its name written down it and a
 * button that unfolds it; and the button that folds it. */
export default function Strip({ name, label, side, onUnfold }:
  { name: string; label: string; side: "left" | "right"; onUnfold: () => void }) {
  return (
    <div className={`ws-strip ${side}`}>
      <button className="bd-ibtn ws-unfold" aria-label={`Unfold ${label}`} title={`Unfold ${label}`} onClick={onUnfold}>
        {side === "left" ? "»" : "«"}</button>
      <span className="ws-strip-name">{name}</span>
    </div>
  );
}

export function FoldButton({ label, side, onFold }: { label: string; side: "left" | "right"; onFold: () => void }) {
  return <button className="bd-ibtn ws-fold" aria-label={`Fold ${label}`} title={`Fold ${label}`} onClick={onFold}>
    {side === "left" ? "«" : "»"}</button>;
}
