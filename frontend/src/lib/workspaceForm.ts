/** The Workspaces page's add and edit form (spec 2026-10-31 §9) (pure): its fields as typed, what the server would refuse
 * (its own rules, spec §5 and §8), "Fill from root", and the body the server takes. */
import type { Detected, WorkspaceFields } from "../api";

export interface FormState {
  name: string; vcs: "p4" | "git"; p4port: string; client: string; p4user: string; root: string;
  compile_commands: string; build_root: string; swarm_url: string; settings: string;
}

export const EMPTY: FormState = { name: "", vcs: "p4", p4port: "", client: "", p4user: "", root: "", compile_commands: "auto",
                                  build_root: "", swarm_url: "", settings: "" };

/** What the server would refuse, by field; empty when the form can be sent. */
export function formErrors(f: FormState): Partial<Record<keyof FormState, string>> {
  const out: Partial<Record<keyof FormState, string>> = {};
  const name = f.name.trim();
  if (!name || [...name].length > 40 || name.includes("/")) out.name = "1–40 characters, no /";
  if (!f.root.trim().startsWith("/")) out.root = "A full path on this host";
  if (!f.p4user.trim()) out.p4user = "The Perforce user its reads run as";
  if (f.vcs === "p4" && !f.p4port.trim()) out.p4port = "A Perforce workspace needs its server";
  if (f.vcs === "p4" && !f.client.trim()) out.client = "A Perforce workspace needs its client";
  return out;
}

/** The form after "Fill from root": what was found fills the fields still empty (the name from the root's folder), the root
 * as found, the compile databases found in place of "auto"; a typed value stays. */
export function withDetected(f: FormState, d: Detected): FormState {
  const keep = (now: string, found: string | null | undefined) => (now.trim() ? now : found ?? now);
  const cc = f.compile_commands.trim();
  return {
    ...f,
    root: d.root || f.root,
    name: keep(f.name, d.root.split("/").filter(Boolean).at(-1)),
    vcs: d.p4port ? "p4" : f.vcs,
    p4port: keep(f.p4port, d.p4port), client: keep(f.client, d.client), p4user: keep(f.p4user, d.p4user),
    compile_commands: (!cc || cc === "auto") && d.compile_commands.length ? d.compile_commands.join("\n") : f.compile_commands,
  };
}

/** A stored workspace, to edit. */
export function fromFields(w: WorkspaceFields): FormState {
  return { name: w.name, vcs: w.vcs, p4port: w.p4port ?? "", client: w.client ?? "", p4user: w.p4user, root: w.root,
           compile_commands: w.compile_commands, build_root: w.build_root ?? "", swarm_url: w.swarm_url ?? "", settings: w.settings };
}

/** The body the server takes: blanks unset, a blank compile database "auto". */
export function toBody(f: FormState): WorkspaceFields {
  const opt = (v: string) => v.trim() || null;
  return { name: f.name.trim(), vcs: f.vcs, p4port: opt(f.p4port), client: opt(f.client), p4user: f.p4user.trim(),
           root: f.root.trim(), compile_commands: f.compile_commands.trim() || "auto", build_root: opt(f.build_root),
           swarm_url: opt(f.swarm_url), settings: f.settings };
}
