import { useCallback, useEffect, useMemo, useState } from "react";
import { useViewState } from "./lib/viewState";
import { TopBar } from "./components/TopBar";
import { IntroScreen } from "./components/IntroScreen";
import { AuthScreen, type AuthCreds } from "./components/AuthScreen";
import { PracticeScreen } from "./components/PracticeScreen";
import { DiagnosticsDrawer } from "./components/DiagnosticsDrawer";
import { ApiError, fetchMe, login, register, type AuthUser } from "./lib/authApi";
import { clearSession, loadSession, saveSession } from "./lib/session";
import type { DiagState, LogLine } from "./lib/mock";

type AuthMode = "login" | "register";

/**
 * App shell — top-level view machine (intro -> auth -> practice; no React Router).
 * C4: auth is REAL (email/password against core_api). Practice/live/analysis
 * remain scripted mock; Google stays mock (not wired in this task).
 */
export function App() {
  // Restore a signed-in session synchronously so we don't flash the intro.
  const restored = useMemo(() => loadSession(), []);
  const { view, go } = useViewState(restored ? "practice" : "intro");

  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [user, setUser] = useState<AuthUser | null>(restored?.user ?? null);
  // The bearer token is persisted via session.ts (localStorage) for later
  // authenticated calls (sessions/grading); C4 doesn't need it in React state.

  // diagnostics / event-log state (mock readouts; auth log lines are real)
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [diag, setDiag] = useState<DiagState>({ googleEnabled: false, gradingMode: "real" });
  const [log, setLog] = useState<LogLine[]>([]);

  const setDiagPart = useCallback((p: Partial<DiagState>) => setDiag((d) => ({ ...d, ...p })), []);
  const addLog = useCallback((m: string) => {
    const t = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLog((L) => [{ t, m }, ...L].slice(0, 40));
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setUser(null);
    addLog("signed out");
    go("intro");
  }, [addLog, go]);

  // Validate a restored token once on mount. Only sign out on a real 401
  // (expired/invalid); keep the optimistic session if the server is unreachable.
  useEffect(() => {
    if (!restored) return;
    let alive = true;
    fetchMe(restored.token)
      .then((u) => {
        if (!alive) return;
        setUser(u);
        saveSession(restored.token, u);
        addLog("GET /api/v1/auth/me → 200 (session restored)");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) {
          addLog("GET /api/v1/auth/me → 401 (session expired)");
          signOut();
        } else {
          addLog("session restore: API unreachable — kept local session");
        }
      });
    return () => {
      alive = false;
    };
  }, [restored, addLog, signOut]);

  const goAuth = useCallback(
    (mode: AuthMode) => {
      setAuthMode(mode);
      go("auth");
    },
    [go],
  );

  // Real email/password auth. Throws ApiError → AuthScreen shows it inline.
  const handleAuthSubmit = useCallback(
    async (mode: AuthMode, creds: AuthCreds) => {
      if (mode === "register") {
        await register({ username: creds.username, email: creds.email, password: creds.password });
        addLog("POST /api/v1/auth/register → 201");
      }
      const tok = await login({ email: creds.email, password: creds.password });
      addLog("POST /api/v1/auth/login → 200; bearer stored");
      const me = await fetchMe(tok);
      addLog("GET /api/v1/auth/me → 200");
      saveSession(tok, me);
      setUser(me);
      go("practice");
    },
    [addLog, go],
  );

  // Google stays mock in C4 — never calls Google endpoints.
  const handleGoogle = useCallback(() => {
    addLog("google sign-in is not wired in this build — use email & password");
  }, [addLog]);

  const [settings, setSettings] = useState({ sttOnly: false, muteTts: false });

  return (
    <div className="p-app">
      <TopBar
        showSession={view === "practice"}
        userName={user?.username ?? ""}
        userInitial={(user?.username ?? "?")[0].toUpperCase()}
        onSignOut={signOut}
        onOpenDiagnostics={() => setDrawerOpen(true)}
      />

      {view === "intro" && <IntroScreen onStart={() => goAuth("register")} onLogin={() => goAuth("login")} />}
      {view === "auth" && (
        <AuthScreen
          mode={authMode}
          setMode={setAuthMode}
          googleEnabled={diag.googleEnabled}
          onSubmit={handleAuthSubmit}
          onGoogle={handleGoogle}
          onBack={() => go("intro")}
        />
      )}
      {view === "practice" && user && (
        <PracticeScreen
          userName={user.username}
          settings={settings}
          setSettings={setSettings}
          gradingMode={diag.gradingMode}
          addLog={addLog}
        />
      )}

      <DiagnosticsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} state={diag} set={setDiagPart} log={log} />
    </div>
  );
}
