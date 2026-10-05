import { useEffect, useState } from "react";

/** The workspace's three layouts (spec 2026-10-04-review-workspace §2.1); follows rotation and resizing. */
export type Screen = "phone" | "tablet" | "desktop";
const PHONE = "(max-width: 640px)", TABLET = "(max-width: 1100px)";
const now = (): Screen => (window.matchMedia(PHONE).matches ? "phone" : window.matchMedia(TABLET).matches ? "tablet" : "desktop");

export function useScreen(): Screen {
  const [screen, setScreen] = useState(now);
  useEffect(() => {
    const qs = [window.matchMedia(PHONE), window.matchMedia(TABLET)], on = () => setScreen(now());
    qs.forEach((q) => q.addEventListener("change", on));
    return () => qs.forEach((q) => q.removeEventListener("change", on));
  }, []);
  return screen;
}
