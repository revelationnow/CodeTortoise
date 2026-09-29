import type { Stage } from "../api";

export default function Stages({ stages }: { stages: Stage[] }) {
  return (
    <ol className="stages">
      {stages.map((s) => (
        <li key={s.name} className={`stage ${s.status}`} title={s.message || s.status}>
          <span className="dot" />
          {s.name.replace("_", " ")}
        </li>
      ))}
    </ol>
  );
}
