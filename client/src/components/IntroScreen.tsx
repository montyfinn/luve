interface IntroScreenProps {
  onContinue: () => void;
}

const POINTS = [
  {
    title: "Speak naturally",
    body: "Just talk. Your words appear as live subtitles while you speak.",
  },
  {
    title: "Real conversation",
    body: "A patient AI tutor listens, thinks, and replies out loud.",
  },
  {
    title: "Feedback & coaching",
    body: "After each session, get a friendly analysis and what to work on next.",
  },
];

/** Intro / landing screen — communicates value and guides to the single next action. */
export function IntroScreen({ onContinue }: IntroScreenProps) {
  return (
    <main className="screen screen--intro">
      <section className="hero card">
        <span className="eyebrow">LUVE · English speaking practice</span>
        <h1 className="hero__title">Practice speaking English with a patient AI tutor</h1>
        <p className="hero__lead">
          Have a real spoken conversation, see what you said transcribed live, and get clear,
          encouraging feedback after each session.
        </p>
        <div className="hero__actions">
          <button type="button" className="btn btn--primary btn--lg" onClick={onContinue}>
            Get started
          </button>
        </div>
      </section>

      <section className="points" aria-label="How it works">
        {POINTS.map((p, i) => (
          <article className="point card" key={p.title}>
            <span className="point__num">{String(i + 1).padStart(2, "0")}</span>
            <h2 className="point__title">{p.title}</h2>
            <p className="point__body">{p.body}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
