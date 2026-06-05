import { useViewState } from "./lib/viewState";
import { IntroScreen } from "./components/IntroScreen";
import { AuthScreen } from "./components/AuthScreen";
import { PracticeScreen } from "./components/PracticeScreen";

/**
 * App shell. Renders one of the three skeleton screens based on the minimal
 * view-state machine. No backend, auth, realtime, or grading wiring yet —
 * navigation between screens is static (button-driven) for this skeleton.
 */
export function App() {
  const { view, go } = useViewState();

  return (
    <div className="app">
      {view === "intro" && <IntroScreen onContinue={() => go("auth")} />}
      {view === "auth" && (
        <AuthScreen onBack={() => go("intro")} onContinue={() => go("practice")} />
      )}
      {view === "practice" && <PracticeScreen onSignOut={() => go("intro")} />}
    </div>
  );
}
