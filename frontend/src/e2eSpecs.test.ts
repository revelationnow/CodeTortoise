import { describe, expect, it } from "vitest";

/** Every e2e spec's source, by path. */
const specs = import.meta.glob<string>("../e2e/*.spec.ts", { query: "?raw", import: "default", eager: true });

describe("the e2e specs", () => {
  it("take `test` from helpers.ts, whose page lets go of a test's stand-ins for the server as it ends", () => {
    expect(Object.keys(specs).length).toBeGreaterThan(20);
    const plain = Object.entries(specs)
      .filter(([, source]) => /import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*["']@playwright\/test["']/.test(source))
      .map(([path]) => path);
    expect(plain, "these take Playwright's own `test`").toEqual([]);
  });
});
