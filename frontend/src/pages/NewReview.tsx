import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export function parseCls(text: string): number[] {
  return [...new Set(text.split(/[\s,]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n > 0))];
}

export default function NewReview() {
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const cls = parseCls(text);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api.createReview(cls, title.trim() || undefined);
      navigate(`/r/${r.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="page narrow">
      <h1>New review</h1>
      <form onSubmit={submit} className="stack">
        <label>
          Changelists (shelved or submitted)
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="12345 12346 12350" />
        </label>
        <div className="muted">{cls.length ? `Will analyse: ${cls.join(", ")}` : "Enter one or more CL numbers."}</div>
        <label>Title (optional)<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button disabled={!cls.length}>Start review</button>
      </form>
    </main>
  );
}
