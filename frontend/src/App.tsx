import { createContext, useContext, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, type Me } from "./api";
import ThemeSwitch from "./components/ThemeSwitch";
import Health from "./pages/Health";
import Login from "./pages/Login";
import NewReview from "./pages/NewReview";
import Review from "./pages/Review";
import Reviews from "./pages/Reviews";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, [location.pathname]);

  if (me === undefined) return <div className="page muted">Loading…</div>;
  if (me === null && location.pathname !== "/login")
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;

  return (
    <MeContext.Provider value={me}>
      <header className="topbar">
        <Link to="/" className="brand">CodeTortoise</Link>
        {me && (
          <nav>
            <Link to="/">Reviews</Link>
            {me.is_owner && <Link to="/new">New review</Link>}
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
        <Route path="/new" element={<NewReview />} />
        <Route path="/health" element={<Health />} />
        <Route path="/r/:id/*" element={<Review />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MeContext.Provider>
  );
}
