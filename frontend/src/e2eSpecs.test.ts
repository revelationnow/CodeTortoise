import { describe, expect, it } from "vitest";

/** Every e2e spec's source, by path: all that Playwright runs under its testDir, e2e (its default testMatch). */
const specs = Object.entries(import.meta.glob<string>("../e2e/**/*.{spec,test}.{ts,tsx,js,jsx,mjs,mts,cjs,cts}",
  { query: "?raw", import: "default", eager: true }));

describe("the e2e specs", () => {
  it("are all read", () => {
    expect(specs.length).toBeGreaterThan(20);
  });

  it("don't take Playwright's own `test`", () => {
    const plain = specs
      .filter(([, source]) => /import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*["']@playwright\/test["']/.test(source))
      .map(([path]) => path);
    expect(plain).toEqual([]);
  });

  // Playwright's `test` is its default export too: a spec that imports it so can't also take helpers.ts's
  it("take `test` from helpers.ts, whose page lets go of a test's stand-ins for the server as it ends", () => {
    const without = specs
      .filter(([, source]) => !/import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*["'](?:\.{1,2}\/)+helpers(?:\.ts)?["']/.test(source))
      .map(([path]) => path);
    expect(without).toEqual([]);
  });
});
