import { useCallback, useState } from "react";
import { useViewState } from "./lib/viewState";
import { TopBar } from "./components/TopBar";
import { IntroScreen } from "./components/IntroScreen";
import { AuthScreen } from "./components/AuthScreen";
import { PracticeScreen } from "./components/PracticeScreen";
import { DiagnosticsDrawer } from "./components/DiagnosticsDrawer";
import type { DiagState, LogLine } from "./lib/mock";

interface User {
  name: string;
  initial: string;
}

type AuthMode = "login" | "register";

/**
 * App shell — top-level view machine (intro -> auth -> practice; no React Router)
 * plus the persistent top bar and the diagnostics drawer. Everything is MOCK:
 * "auth" just sets a local user and advances; no backend/realtime/grading.
 */
export function App() {
  const { view, go } = useViewState();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [user, setUser] = useState<User | null>(null);

  // diagnostics / event-log state (mock)
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [diag, setDiag] = useState<DiagState>({ googleEnabled: false, gradingMode: "real" });
  const [log, setLog] = useState<LogLine[]>([]);

  const setDiagPart = useCallback((p: Partial<DiagState>) => setDiag((d) => ({ ...d, ...p })), []);
  const addLog = useCallback((m: string) => {
    const t = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLog((L) => [{ t, m }, ...L].slice(0, 40));
  }, []);

  const goAuth = useCallback(
    (mode: AuthMode) => {
      setAuthMode(mode);
      go("auth");
    },
    [go],
  );

  const handleAuth = useCallback(
    (name: string) => {
      const display = name && name !== "there" ? name : "Maria";
      setUser({ name: display, initial: display[0].toUpperCase() });
      addLog("POST /api/v1/auth/login → 200; bearer stored  [mock]");
      go("practice");
    },
    [addLog, go],
  );

  const handleGoogle = useCallback(() => {
    if (!diag.googleEnabled) {
      addLog("404 /api/v1/auth/google/start (paused)  [mock]");
      return;
    }
    addLog("302 → accounts.google.com; google_code → exchange → 200  [mock]");
    setUser({ name: "Maria", initial: "M" });
    go("practice");
  }, [diag.googleEnabled, addLog, go]);

  const signOut = useCallback(() => {
    setUser(null);
    addLog("signed out  [mock]");
    go("intro");
  }, [addLog, go]);

  const [settings, setSettings] = useState({ sttOnly: false, muteTts: false });

  return (
    <div className="p-app">
      <TopBar
        showSession={view === "practice"}
        userName={user?.name ?? ""}
        userInitial={user?.initial ?? ""}
        onSignOut={signOut}
        onOpenDiagnostics={() => setDrawerOpen(true)}
      />

      {view === "intro" && <IntroScreen onStart={() => goAuth("register")} onLogin={() => goAuth("login")} />}
      {view === "auth" && (
        <AuthScreen
          mode={authMode}
          setMode={setAuthMode}
          googleEnabled={diag.googleEnabled}
          onSubmit={handleAuth}
          onGoogle={handleGoogle}
          onBack={() => go("intro")}
        />
      )}
      {view === "practice" && user && (
        <PracticeScreen
          userName={user.name}
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
