import { useState } from "react";

interface Settings {
  sttOnly: boolean;
  muteTts: boolean;
}

interface HomeProps {
  userName: string;
  onStart: () => void;
  settings: Settings;
  setSettings: (s: Settings) => void;
}

/** Authenticated home — primary "Start practice" + a quiet practice-settings disclosure. */
export function Home({ userName, onStart, settings, setSettings }: HomeProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-home">
          <div
            className="p-eyebrow"
            style={{ color: "var(--ink-3)", letterSpacing: ".04em", textTransform: "none", fontSize: "var(--t-sm)" }}
          >
            Welcome back, {userName}
          </div>
          <h2>Ready for a conversation?</h2>
          <p>Find a quiet spot, allow your microphone, and start talking. The tutor will respond out loud.</p>
          <button className="btn btn--primary btn--xl" onClick={onStart}>
            Start practice
          </button>

          <div className="p-settings">
            <button className="p-disclosure" aria-expanded={open} onClick={() => setOpen(!open)}>
              <span style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }}>⌄</span>{" "}
              Practice settings
              <span style={{ color: "var(--hairline-2)" }}>·</span>{" "}
              <span style={{ color: "var(--ink-4)" }}>One session at a time</span>
            </button>
            {open && (
              <div className="p-settings__body">
                <div className="p-toggle-row">
                  <div className="lbl">
                    <b>Transcript only</b>
                    <span>Practice without the tutor's voice (STT only).</span>
                  </div>
                  <button
                    className={"p-switch" + (settings.sttOnly ? " on" : "")}
                    aria-pressed={settings.sttOnly}
                    aria-label="Transcript only"
                    onClick={() => setSettings({ ...settings, sttOnly: !settings.sttOnly })}
                  />
                </div>
                <div className="p-toggle-row">
                  <div className="lbl">
                    <b>Mute tutor audio</b>
                    <span>See replies as text, no spoken audio.</span>
                  </div>
                  <button
                    className={"p-switch" + (settings.muteTts ? " on" : "")}
                    aria-pressed={settings.muteTts}
                    aria-label="Mute tutor audio"
                    onClick={() => setSettings({ ...settings, muteTts: !settings.muteTts })}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
