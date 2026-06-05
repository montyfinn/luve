interface IntroScreenProps {
  onStart: () => void; // -> auth (register intent)
  onLogin: () => void; // -> auth (login intent)
}

/** Landing — two-column hero with editorial headline + "how it works" card. */
export function IntroScreen({ onStart, onLogin }: IntroScreenProps) {
  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-hero">
          <div>
            <p className="p-eyebrow">Speaking practice, with an AI coach</p>
            <h1>
              Practice speaking English, out loud, <em>without the nerves.</em>
            </h1>
            <p>
              Have a real spoken conversation with an AI tutor. When you're done, get calm,
              specific coaching on your fluency, grammar and vocabulary.
            </p>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <button className="btn btn--primary" onClick={onStart}>
                Start practicing
              </button>
              <button className="btn btn--ghost" onClick={onLogin}>
                I already have an account
              </button>
            </div>
            <p className="p-note" style={{ marginTop: "24px" }}>
              A focused demo build — one practice session at a time.
            </p>
          </div>
          <div className="p-card p-howcard">
            <p className="p-eyebrow" style={{ marginBottom: "18px" }}>
              How a session works
            </p>
            <div className="p-howstep">
              <span className="num">1</span>
              <div>
                <div style={{ fontWeight: 600 }}>Speak naturally</div>
                <div style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>
                  Your mic streams to the tutor in real time.
                </div>
              </div>
            </div>
            <div className="p-howstep">
              <span className="num">2</span>
              <div>
                <div style={{ fontWeight: 600 }}>Listen &amp; respond</div>
                <div style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>
                  The tutor replies out loud — a real back-and-forth.
                </div>
              </div>
            </div>
            <div className="p-howstep">
              <span className="num">3</span>
              <div>
                <div style={{ fontWeight: 600 }}>Get coaching</div>
                <div style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>
                  End the session for scores and specific corrections.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
