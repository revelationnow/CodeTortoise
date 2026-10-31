import { describe, expect, it } from "vitest";
import { EMPTY, formErrors, fromFields, toBody, withDetected } from "./workspaceForm";

const OK = { ...EMPTY, name: "dsp", vcs: "git" as const, p4user: "amy", root: "/work/dsp" };
const FOUND = { root: "/work/dsp", p4port: "ssl:p4:1666", client: "amy-dsp", p4user: "amy",
                compile_commands: ["/work/dsp/build/compile_commands.json"], client_root: "/work/dsp", notes: [] };

describe("the Workspaces page's form (spec 2026-10-31 §9)", () => {
  it("can send a git workspace with a name, a user and a full root", () => {
    expect(formErrors(OK)).toEqual({});
  });

  it("says, by field, what the server would refuse", () => {
    expect(Object.keys(formErrors(EMPTY)).sort()).toEqual(["client", "name", "p4port", "p4user", "root"]);
    expect(formErrors({ ...OK, name: "a/b" }).name).toBe("1–40 characters, no /");
    expect(formErrors({ ...OK, name: "x".repeat(41) }).name).toBe("1–40 characters, no /");
    expect(formErrors({ ...OK, name: "x".repeat(40) }).name).toBeUndefined();
    expect(formErrors({ ...OK, root: "work/dsp" }).root).toBe("A full path on this host");
    expect(formErrors({ ...OK, vcs: "p4", p4port: "ssl:p4:1666" })).toEqual({ client: "A Perforce workspace needs its client" });
  });

  it("fills from the root what is still empty, and keeps what was typed", () => {
    expect(withDetected({ ...EMPTY, root: "/work/dsp/" }, FOUND)).toEqual({ ...EMPTY, name: "dsp", root: "/work/dsp",
      p4port: "ssl:p4:1666", client: "amy-dsp", p4user: "amy", compile_commands: "/work/dsp/build/compile_commands.json" });
    const typed = withDetected({ ...OK, name: "mine", p4user: "bob", compile_commands: "/elsewhere/compile_commands.json" }, FOUND);
    expect([typed.name, typed.p4user, typed.compile_commands, typed.vcs]).toEqual(["mine", "bob", "/elsewhere/compile_commands.json", "p4"]);
    expect(withDetected(OK, { ...FOUND, p4port: null, client: null, p4user: null, compile_commands: [] })).toEqual(OK);
  });

  it("sends blanks as unset and a blank compile database as auto; an edit starts from what is stored", () => {
    expect(toBody({ ...OK, name: " dsp ", swarm_url: "  ", compile_commands: " " })).toEqual({
      name: "dsp", vcs: "git", p4port: null, client: null, p4user: "amy", root: "/work/dsp", compile_commands: "auto",
      build_root: null, swarm_url: null, settings: "" });
    const stored = toBody({ ...OK, p4port: "second:1666", settings: "analysis: {sink_threshold: 3}" });
    expect(fromFields(stored)).toEqual({ ...OK, p4port: "second:1666", settings: "analysis: {sink_threshold: 3}" });
  });
});
