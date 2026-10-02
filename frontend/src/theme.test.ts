import { afterEach, describe, expect, it, vi } from "vitest";
import { parseChoice, resolveTheme } from "./theme";

afterEach(() => vi.unstubAllGlobals());

describe("theme", () => {
  it("follows the system unless the viewer chose", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("treats a missing or bad stored choice as system", () => {
    expect(parseChoice(null)).toBe("system");
    expect(parseChoice('"dark"')).toBe("dark");
    expect(parseChoice('"sepia"')).toBe("system");
    expect(parseChoice("{not json")).toBe("system");
    expect(parseChoice("dark")).toBe("system");           // stored values are JSON, like every other pref
  });
});
