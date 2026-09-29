import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

export default function Login({ onLogin }: { onLogin: () => Promise<unknown> }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(user.trim(), password);
      await onLogin();
      navigate(params.get("next") || "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page narrow">
      <h1>Sign in</h1>
      <p className="muted">Use your Perforce credentials.</p>
      <form onSubmit={submit} className="stack">
        <label>P4 user<input autoFocus value={user} onChange={(e) => setUser(e.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button disabled={busy || !user.trim()}>{busy ? "Checking…" : "Sign in"}</button>
      </form>
    </main>
  );
}
