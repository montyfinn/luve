/**
 * Minimal app view-state machine (migration plan decision: no React Router yet).
 *
 * The skeleton has three top-level views and a single linear happy path:
 *   intro -> auth -> practice
 * with back-navigation where it makes sense. This stays a tiny, explicit state
 * model; a router is introduced later only if real routes / deep links appear
 * (session history, settings, shareable analysis) — see the migration plan.
 */
import { useCallback, useMemo, useState } from "react";

export type View = "intro" | "auth" | "practice";

export const INITIAL_VIEW: View = "intro";

/** Allowed transitions out of each view. Keeps navigation explicit + reviewable. */
const TRANSITIONS: Record<View, View[]> = {
  intro: ["auth"],
  auth: ["intro", "practice"],
  practice: ["intro"],
};

export function canNavigate(from: View, to: View): boolean {
  return TRANSITIONS[from].includes(to);
}

export interface ViewController {
  view: View;
  go: (to: View) => void;
}

export function useViewState(initial: View = INITIAL_VIEW): ViewController {
  const [view, setView] = useState<View>(initial);

  const go = useCallback(
    (to: View) => {
      setView((current) => (canNavigate(current, to) ? to : current));
    },
    [],
  );

  return useMemo(() => ({ view, go }), [view, go]);
}
