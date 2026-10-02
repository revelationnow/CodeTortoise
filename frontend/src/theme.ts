/** Light/dark theme (spec §11): the viewer's choice (System, Light, Dark; remembered per browser) resolved against
 * the OS setting, applied as `data-theme` + `color-scheme` on <html> so native controls match the page. */
import { useEffect, useState } from "react";

export type Choice = "system" | "light" | "dark";
export type Theme = "light" | "dark";
export const THEME_KEY = "ct.theme";

export function parseChoice(raw: string | null): Choice {
  try {
    const v = raw === null ? null : JSON.parse(raw);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export const resolveTheme = (choice: Choice, systemDark: boolean): Theme =>
  choice === "system" ? (systemDark ? "dark" : "light") : choice;

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

function storedChoice(): Choice {
  try {
    return parseChoice(window.localStorage.getItem(THEME_KEY));
  } catch {
    return "system";
  }
}

export function useTheme(): [Choice, (c: Choice) => void] {
  const [choice, setChoice] = useState<Choice>(storedChoice);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => applyTheme(resolveTheme(choice, mq.matches));
    apply();
    mq.addEventListener("change", apply);                // System follows the OS live
    return () => mq.removeEventListener("change", apply);
  }, [choice]);
  const choose = (c: Choice) => {
    try {
      window.localStorage.setItem(THEME_KEY, JSON.stringify(c));
    } catch {
      /* not remembered; still applied */
    }
    setChoice(c);
  };
  return [choice, choose];
}
