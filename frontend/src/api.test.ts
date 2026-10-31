import { describe, expect, it, vi } from "vitest";
import { api, ApiError, errorText } from "./api";

describe("errorText", () => {
  const FALLBACK = "The server did not accept the mark.";

  it("is the words of an error that has some", () => {
    expect(errorText(new ApiError(500, "the store is busy"), FALLBACK)).toBe("the store is busy");
    expect(errorText(new TypeError("Failed to fetch"), FALLBACK)).toBe("Failed to fetch");
    expect(errorText(new Error(" spaced out "), FALLBACK)).toBe("spaced out");
  });

  it("is the fallback for a refusal with no words: no detail and, over HTTP/2, no status text", () => {
    expect(errorText(new ApiError(500, ""), FALLBACK)).toBe(FALLBACK);
    expect(errorText(new Error("   "), FALLBACK)).toBe(FALLBACK);
  });

  it("is a thing thrown that is no error, if it is words, and the fallback otherwise", () => {
    expect(errorText("it broke", FALLBACK)).toBe("it broke");
    expect(errorText({ message: "it broke" }, FALLBACK)).toBe("it broke");
    for (const nothing of ["", "  ", undefined, null, 0, {}, { message: undefined }, { message: 42 }])
      expect(errorText(nothing, FALLBACK), JSON.stringify(nothing)).toBe(FALLBACK);
  });
});

describe("a refusal that names a Perforce server", () => {
  it("carries the server a review asks the session to sign in to (spec 2026-10-31 §7), and none otherwise", async () => {
    const refused = (status: number, body: object) => vi.stubGlobal("fetch", async () => new Response(JSON.stringify(body), { status }));
    const failure = () => api.review(7).then(() => null, (e: unknown) => e as ApiError);
    try {
      refused(401, { detail: "sign in required", server: "second:1666" });
      const e = await failure();
      expect(e).toBeInstanceOf(ApiError);
      expect([e?.status, e?.message, e?.server]).toEqual([401, "sign in required", "second:1666"]);
      refused(403, { detail: "owner only" });
      expect((await failure())?.server).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
