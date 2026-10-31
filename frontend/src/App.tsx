import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, type Me } from "./api";
import InsecureBanner from "./components/InsecureBanner";
import Logo from "./components/Logo";
import ThemeSwitch from "./components/ThemeSwitch";
import { accountLabel } from "./lib/signin";
import Health from "./pages/Health";
import Login from "./pages/Login";
import Reviews from "./pages/Reviews";
import Workspace from "./workspace/Workspace";

/** One workspace per review: moving to another review starts it afresh, so nothing of the last one (an error, its
 * memory, a late answer) carries over. */
function ReviewRoute() {
  const { id } = useParams();
  return <Workspace key={id} />;
}

/** `/w/` was the workspace's address while it was built; it is `/r/` now. */
function ToReview() {
  const { id, "*": rest } = useParams(), { search, hash } = useLocation();
  return <Navigate to={`/r/${id}${rest ? `/${rest}` : ""}${search}${hash}`} replace />;
}

/** A workspace's Health page, afresh for each workspace (spec 2026-10-31 §9). */
function HealthRoute() {
  const { id } = useParams();
  return <Health key={id} wid={Number(id)} />;
}

/** `/health` was the one workspace's Health page; each workspace has its own now (spec 2026-10-31 §8). */
function ToHealth() {
  const first = useMe()?.owner_of[0];
  return <Navigate to={first === undefined ? "/" : `/workspaces/${first}`} replace />;
}

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);
const RefreshMeContext = createContext<() => Promise<unknown>>(() => Promise.resolve());
/** Load the session again, so the top bar follows a sign-in made in place (a review's prompt). */
export const useRefreshMe = () => useContext(RefreshMeContext);

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const location = useLocation();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const refreshMe = useCallback(() => api.me().then(setMe), []);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
    setMenu(false);
  }, [location.pathname]);

  if (me === undefined) return <div className="page muted">Loading…</div>;
  if (me === null && location.pathname !== "/login")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  const here = location.pathname === "/login" ? "/" : location.pathname + location.search;

  return (
    <MeContext.Provider value={me}>
      <RefreshMeContext.Provider value={refreshMe}>
        <InsecureBanner />
        <header className={`topbar${menu ? " open" : ""}`}>
          <Link to="/" className="brand"><Logo size={28} />CodeTortoise</Link>
          {me && (
            <button className="menu-btn" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button>
          )}
          {me && (
            <nav>
              <Link to="/">Reviews</Link>
              {me.owner_of.length > 0 && <Link to="/health">Health</Link>}
              {/* the account menu (spec 2026-10-31 §9): a line per sign-in, and signing in to another server; shut again on
                  each move */}
              <details className="account" key={location.pathname}>
                <summary>{accountLabel(me.logins)}</summary>
                <ul>
                  {me.logins.map((l) => <li key={l.server}>{l.server} as {l.user}</li>)}
                  <li><Link to={`/login?next=${encodeURIComponent(here)}`}>Sign in to another server</Link></li>
                </ul>
              </details>
              <button className="link" onClick={() => api.logout().then(() => { setMe(null); navigate("/login"); })}>
                Log out
              </button>
            </nav>
          )}
          <ThemeSwitch />
        </header>
        <Routes>
          <Route path="/login" element={<Login onLogin={refreshMe} />} />
          <Route path="/" element={<Reviews />} />
          <Route path="/new" element={<Navigate to="/" replace />} />
          <Route path="/health" element={<ToHealth />} />
          <Route path="/workspaces/:id" element={<HealthRoute />} />
          <Route path="/r/:id/*" element={<ReviewRoute />} />
          <Route path="/w/:id/*" element={<ToReview />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </RefreshMeContext.Provider>
    </MeContext.Provider>
  );
}
