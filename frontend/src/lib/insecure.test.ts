import { describe, expect, it } from "vitest";
import { plainHttpOnNetwork } from "./insecure";

describe("plain-HTTP banner rule (spec §14.2)", () => {
  it("shows for http on a network host", () => {
    expect(plainHttpOnNetwork("http:", "192.168.1.122")).toBe(true);
    expect(plainHttpOnNetwork("http:", "codetortoise.example.com")).toBe(true);
    expect(plainHttpOnNetwork("http:", "[fe80::1]")).toBe(true);
  });

  it("hides for https and for loopback hosts", () => {
    expect(plainHttpOnNetwork("https:", "192.168.1.122")).toBe(false);
    for (const h of ["localhost", "127.0.0.1", "127.1.2.3", "[::1]"]) expect(plainHttpOnNetwork("http:", h)).toBe(false);
  });
});
