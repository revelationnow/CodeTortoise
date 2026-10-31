import { type FormEvent, useEffect, useState } from "react";
import { api, errorText, type ServerRow } from "../api";
import { pickerShown, startServer } from "../lib/signin";
import Logo from "./Logo";

/** The sign-in form (spec 2026-10-31 §9): the Perforce server (a picker, hidden with one server), the user and the password.
 * `fixed`: the server a review asks for (its prompt says so, and there is no picker); `asked`: the server to start on.
 * `onDone` runs once the server accepts the sign-in; the button waits for it. */
export default function SignInForm({ fixed = null, asked = null, onDone }:
  { fixed?: string | null; asked?: string | null; onDone: () => Promise<unknown> }) {
  const [servers, setServers] = useState<ServerRow[] | null>(null);
  const [server, setServer] = useState<string | null>(fixed);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (fixed) return;
    api.servers().then((s) => { setServers(s); setServer((now) => now ?? startServer(s, asked)); })
      .catch(() => setServers([]));                 // the server then takes the only one there is, or says to choose
  }, [fixed, asked]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(server, user.trim(), password);
      await onDone();
    } catch (err) {
      setError(errorText(err, "You could not be signed in."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="login-card stack">
      <Logo size={64} />
      <h1>CodeTortoise</h1>
      <p className="muted">{fixed ? `Sign in to ${fixed} to open this review` : "Sign in with your Perforce account"}</p>
      {servers && pickerShown(servers, fixed) && (
        <label>Perforce server
          <select value={server ?? ""} onChange={(e) => setServer(e.target.value)}>
            {servers.map((s) => <option key={s.server} value={s.server}>{s.server}{s.user ? ` (signed in as ${s.user})` : ""}</option>)}
          </select>
        </label>
      )}
      <label>P4 user<input autoFocus value={user} onChange={(e) => setUser(e.target.value)} required /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      {error && <div className="error" role="alert">{error}</div>}
      {/* until the servers are known, the one to sign in to isn't */}
      <button className="go" disabled={busy || !user.trim() || (!fixed && servers === null)}>{busy ? "Checking…" : "Sign in"}</button>
    </form>
  );
}
