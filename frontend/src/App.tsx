import { type ReactNode, useEffect } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { SignIn, SignUp, SignedIn, UserButton, useAuth } from "@clerk/clerk-react";
import { BarChart3, FlaskConical, Image, LayoutDashboard, Rocket, Settings2, type LucideIcon } from "lucide-react";
import { AdminPage } from "./pages/AdminPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DebugPage } from "./pages/DebugPage";
import { GalleryPage } from "./pages/GalleryPage";
import { IntakePage } from "./pages/IntakePage";
import { PlaygroundPage } from "./pages/PlaygroundPage";
import { setAuthTokenProvider } from "./lib/api";
import { useCampaignStore } from "./store/campaignStore";

const AUTH_MODE = String(import.meta.env.VITE_AUTH_MODE ?? "clerk").toLowerCase();
const AUTH_ENABLED = AUTH_MODE !== "disabled";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
};

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/intake", label: "Campaigns", icon: Rocket },
  { to: "/admin", label: "Analytics", icon: BarChart3 },
  { to: "/playground", label: "Playground", icon: FlaskConical },
  { to: "/gallery", label: "Gallery", icon: Image },
  { to: "/debug", label: "Settings", icon: Settings2 },
];

function AppShell({
  children,
  showUserButton,
}: {
  children: ReactNode;
  showUserButton: boolean;
}) {
  const location = useLocation();
  const isAuthRoute = location.pathname.startsWith("/sign-in") || location.pathname.startsWith("/sign-up");

  useEffect(() => {
    if (typeof document === "undefined" || isAuthRoute) {
      return;
    }
    document.body.classList.remove("theme-dark");
    document.body.classList.add("theme-light");
  }, [isAuthRoute]);

  if (isAuthRoute) {
    return <main className="auth-page-root">{children}</main>;
  }

  return (
    <div className="saas-shell">
      <div className="saas-main">
        <header className="top-navbar">
          <div className="top-navbar-left">
            <div className="top-nav-brand">
              <p className="sidebar-kicker">Open Pomelli</p>
              <h1>Nexus Dashboard</h1>
            </div>
            <nav className="top-nav-links" aria-label="Primary">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => (isActive ? "top-nav-link top-nav-link-active" : "top-nav-link")}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>
          <div className="top-navbar-actions">
            {showUserButton ? (
              <SignedIn>
                <div className="top-user-chip">
                  <UserButton />
                </div>
              </SignedIn>
            ) : (
              <div className="top-user-fallback">OP</div>
            )}
          </div>
        </header>

        <main className="page-root">{children}</main>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return (
      <section className="page-root">
        <p>Loading authentication...</p>
      </section>
    );
  }
  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />;
  }
  return <>{children}</>;
}

function ClerkApp() {
  const initialize = useCampaignStore((state) => state.initialize);
  const { getToken } = useAuth();

  useEffect(() => {
    setAuthTokenProvider(async () => {
      const token = await getToken();
      return token ?? null;
    });
    return () => setAuthTokenProvider(null);
  }, [getToken]);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  return (
    <AppShell showUserButton>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />} />
        <Route path="/sign-up/*" element={<SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />} />
        <Route
          path="/intake"
          element={
            <ProtectedRoute>
              <IntakePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/gallery"
          element={
            <ProtectedRoute>
              <GalleryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/debug"
          element={
            <ProtectedRoute>
              <DebugPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute>
              <AdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/playground"
          element={
            <ProtectedRoute>
              <PlaygroundPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}

function LocalDevApp() {
  const initialize = useCampaignStore((state) => state.initialize);

  useEffect(() => {
    setAuthTokenProvider(null);
    void initialize();
  }, [initialize]);

  return (
    <AppShell showUserButton={false}>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/sign-in/*" element={<Navigate to="/dashboard" replace />} />
        <Route path="/sign-up/*" element={<Navigate to="/dashboard" replace />} />
        <Route path="/intake" element={<IntakePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/debug" element={<DebugPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/playground" element={<PlaygroundPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}

export default function App() {
  return AUTH_ENABLED ? <ClerkApp /> : <LocalDevApp />;
}
