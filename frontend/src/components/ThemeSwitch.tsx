import { type Choice, useTheme } from "../theme";

const OPTIONS: [Choice, string, string][] = [["system", "◐", "System theme"], ["light", "☀", "Light theme"], ["dark", "☾", "Dark theme"]];

/** System / Light / Dark switch for the top bar. */
export default function ThemeSwitch() {
  const [choice, choose] = useTheme();
  return (
    <span className="theme-switch" role="group" aria-label="Theme">
      {OPTIONS.map(([c, icon, label]) => (
        <button key={c} type="button" className={choice === c ? "on" : ""} aria-label={label} aria-pressed={choice === c}
                title={label} onClick={() => choose(c)}>{icon}</button>
      ))}
    </span>
  );
}
