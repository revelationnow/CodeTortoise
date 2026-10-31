/** Sign-in per Perforce server (spec 2026-10-31 §7, §9) (pure): what the sign-in form offers and what the account menu says. */
import type { Login, ServerRow } from "../api";

/** The picker shows only when there is a choice: several servers, and no server fixed by the review asking. */
export function pickerShown(servers: ServerRow[], fixed?: string | null): boolean {
  return !fixed && servers.length > 1;
}

/** The server the form starts on: the one asked for, else the first the session isn't signed in to, else the first. */
export function startServer(servers: ServerRow[], asked?: string | null): string | null {
  if (asked && servers.some((s) => s.server === asked)) return asked;
  return (servers.find((s) => !s.user) ?? servers[0])?.server ?? null;
}

/** The account menu's button: the first sign-in's user, and how many more sign-ins there are ("amy +1"). */
export function accountLabel(logins: Login[]): string {
  if (!logins.length) return "";
  return logins.length > 1 ? `${logins[0].user} +${logins.length - 1}` : logins[0].user;
}

/** The session's user on `server`, or null. */
export function userOn(logins: Login[], server: string | undefined): string | null {
  return logins.find((l) => l.server === server)?.user ?? null;
}
