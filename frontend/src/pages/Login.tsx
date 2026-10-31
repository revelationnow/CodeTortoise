import { useNavigate, useSearchParams } from "react-router-dom";
import SignInForm from "../components/SignInForm";

/** The sign-in page (spec 2026-10-31 §9): `?server=` starts the form on that server, `?next=` is where it goes after. */
export default function Login({ onLogin }: { onLogin: () => Promise<unknown> }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  return (
    <main className="login-wrap">
      <SignInForm asked={params.get("server")} onDone={async () => { await onLogin(); navigate(params.get("next") || "/"); }} />
    </main>
  );
}
