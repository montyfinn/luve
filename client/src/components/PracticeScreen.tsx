import { DiagnosticsPanel } from "./DiagnosticsPanel";

interface PracticeScreenProps {
  onSignOut: () => void;
}

/**
 * Practice / conversation shell — STATIC PLACEHOLDERS ONLY. No realtime, mic,
 * transcript, or grading wiring in this skeleton. Sections are laid out so later
 * phases can fill them in: primary action, live status, transcript, analysis,
 * and a collapsible diagnostics panel.
 */
export function PracticeScreen({ onSignOut }: PracticeScreenProps) {
  return (
    <main className="screen screen--practice">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__logo">LUVE</span>
          <span className="topbar__divider">·</span>
          <span className="topbar__title">Speaking Practice</span>
        </div>
        <div className="topbar__actions">
          <span className="chip chip--idle">Idle</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>

      {/* Primary action — the one obvious next step. */}
      <section className="card hero hero--practice">
        <div className="hero__text">
          <h1 className="hero__title hero__title--sm">Ready to practise?</h1>
          <p className="hero__lead">
            Start a live session and speak with your AI tutor. Your words appear below, and a
            friendly analysis follows when you finish.
          </p>
        </div>
        <button type="button" className="btn btn--primary btn--lg" disabled aria-disabled="true">
          Start practice
        </button>
      </section>

      <div className="practice-grid">
        {/* Live transcript placeholder (two tiers). */}
        <section className="card section">
          <div className="section__head">
            <h2 className="section__title">Live transcript</h2>
            <span className="section__hint">Appears while you speak</span>
          </div>
          <div className="transcript">
            <div className="transcript__block">
              <p className="transcript__label">Final</p>
              <div className="transcript__final empty-state">Your finalized speech will show here.</div>
            </div>
            <div className="transcript__block">
              <p className="transcript__label">Partial</p>
              <div className="transcript__partial empty-state">Live hypothesis…</div>
            </div>
          </div>
        </section>

        {/* Analysis / feedback placeholder. */}
        <section className="card section">
          <div className="section__head">
            <h2 className="section__title">Session analysis</h2>
            <span className="section__hint">After you finish</span>
          </div>
          <div className="scorecards">
            {["Overall", "Fluency", "Grammar", "Vocabulary"].map((label) => (
              <div className="scorecard" key={label}>
                <span className="scorecard__label">{label}</span>
                <span className="scorecard__value">—</span>
              </div>
            ))}
          </div>
          <p className="empty-state empty-state--block">
            Your analysis — scores, corrections, and coaching tips — will appear here after a
            session.
          </p>
        </section>
      </div>

      <DiagnosticsPanel />
    </main>
  );
}
