import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pollLoop } from "./poll";

describe("pollLoop", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("waits for each poll to finish before scheduling the next", async () => {
    let calls = 0, done: () => void = () => {};
    const stop = pollLoop(() => { calls++; return new Promise<void>((r) => { done = r; }); }, 1500);
    await vi.advanceTimersByTimeAsync(1500);
    expect(calls).toBe(1);
    await vi.advanceTimersByTimeAsync(10_000);                // still waiting on the first: no pile-up
    expect(calls).toBe(1);
    done();
    await vi.advanceTimersByTimeAsync(1500);
    expect(calls).toBe(2);
    stop();
  });

  it("keeps going after a failed poll, and stops when told", async () => {
    let calls = 0;
    const stop = pollLoop(() => { calls++; return Promise.reject(new Error("offline")); }, 1000);
    await vi.advanceTimersByTimeAsync(3000);
    expect(calls).toBe(3);
    stop();
    await vi.advanceTimersByTimeAsync(5000);
    expect(calls).toBe(3);
  });
});
