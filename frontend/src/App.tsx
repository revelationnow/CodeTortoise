import { createContext, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, type Me } from "./api";
import InsecureBanner from "./components/InsecureBanner";
import Logo from "./components/Logo";
import ThemeSwitch from "./components/ThemeSwitch";
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

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const location = useLocation();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
    setMenu(false);
  }, [location.pathname]);

  if (me === undefined) return <div className="page muted">Loading…</div>;
  if (me === null && location.pathname !== "/login")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;

  return (
    <MeContext.Provider value={me}>
      <InsecureBanner />
      <header className={`topbar${menu ? " open" : ""}`}>
        <Link to="/" className="brand"><Logo size={28} />CodeTortoise</Link>
        {me && (
          <button className="menu-btn" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button>
        )}
        {me && (
          <nav>
            <Link to="/">Reviews</Link>
            {me.is_owner && <Link to="/health">Health</Link>}
            <span className="muted">{me.user}</span>
            <button className="link" onClick={() => api.logout().then(() => { setMe(null); navigate("/login"); })}>
              Log out
            </button>
          </nav>
        )}
        <ThemeSwitch />
      </header>
      <Routes>
        <Route path="/login" element={<Login onLogin={() => api.me().then(setMe)} />} />
        <Route path="/" element={<Reviews />} />
        <Route path="/new" element={<Navigate to="/" replace />} />
        <Route path="/health" element={<Health />} />
        <Route path="/r/:id/*" element={<ReviewRoute />} />
        <Route path="/w/:id/*" element={<ToReview />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MeContext.Provider>
  );
}
