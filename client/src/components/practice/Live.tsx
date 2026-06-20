import { useEffect, useRef } from "react";
import { PHASE_META, type Phase } from "../../lib/mock";
import { hasTimings, type RealtimeTimingView } from "../../lib/realtimeTimeline";
import { MicIcon, MicOffIcon, InterruptIcon, PowerIcon } from "../icons";

export interface Turn {
  who: "ai" | "you";
  text: string;
}

interface LiveProps {
  phase: Phase;
  transcript: Turn[];
  partial: string;
  /** Streaming assistant text (assistant_stream deltas) before assistant_final. */
  assistantPartial?: string;
  /** Compact client-side realtime timings; null when none yet. */
  timing?: RealtimeTimingView | null;
  muted: boolean;
  elapsed: number;
  /** Safe realtime error message (mic/gateway/engine); null when none. */
  error?: string | null;
  speechHint?: string | null;
  authExpiryWarning?: "soon" | "urgent" | null;
  onMute: () => void;
  onInterrupt: () => void;
  onEnd: () => void;
}

/** Live conversation shell. Orb carries state; transcript builds turn-by-turn.
 *  Realtime/WebRTC ownership stays in PracticeScreen; this component renders
 *  the live state it receives from the active session flow. */
export function Live({
  phase,
  transcript,
  partial,
  assistantPartial = "",
  timing = null,
  muted,
  elapsed,
  error,
  speechHint = null,
  authExpiryWarning = null,
  onMute,
  onInterrupt,
  onEnd,
}: LiveProps) {
  const meta = PHASE_META[phase] ?? PHASE_META.listening;
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [transcript, partial, assistantPartial]);

  // Space toggles the mic from anywhere in the live screen — not only when the
  // mute button happens to be focused — so it works immediately once a session
  // is active. preventDefault stops page scroll and the native button
  // activation, so the mute button never double-toggles.
  useEffect(() => {
    function isTypingTarget(el: EventTarget | null): boolean {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      return (
        el.isContentEditable ||
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT"
      );
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space" && e.key !== " ") return;
      if (e.repeat) return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      onMute();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onMute]);

  const orbClass =
    "p-orb " + (muted && phase !== "thinking" && phase !== "aispeaking" ? "muted " : "") + meta.orb;
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  const mutedLabel = muted && (phase === "listening" || phase === "speaking");

  return (
    <div className="p-view p-main">
      <div className="p-wrap">
        <div className="p-live">
          <div className="p-live__bar">
            <span className={"p-chip p-chip--" + meta.chip[0]}>
              <span className="d" />
              {meta.chip[1]}
            </span>
            <span style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>
              Practice session · {mm}:{ss}
            </span>
            <button className="btn btn--danger" onClick={onEnd}>
              <PowerIcon size={15} />
              End session
            </button>
          </div>

          {authExpiryWarning && (
            <div
              className={`p-live-auth p-live-auth--${authExpiryWarning}`}
              role="alert"
              aria-live={authExpiryWarning === "urgent" ? "assertive" : "polite"}
            >
              <span>Your sign-in session is ending soon. End now to save and grade this practice.</span>
              <button className="btn btn--primary" onClick={onEnd}>
                End and grade now
              </button>
            </div>
          )}

          {phase === "connecting" ? (
            // cat/Lottie connecting animation deferred to motion phase — CSS spinner stand-in
            <div className="p-connecting">
              <div className="p-spinner" />
            </div>
          ) : (
            <div className={orbClass}>
              <div className="p-orb__ring" />
              <div className="p-orb__ring r2" />
              <div className="p-orb__core">
                {phase === "thinking" ? (
                  <span className="p-think">
                    <i />
                    <i />
                    <i />
                  </span>
                ) : phase === "aispeaking" ? (
                  <span className="p-wave">
                    <i />
                    <i />
                    <i />
                    <i />
                    <i />
                  </span>
                ) : muted ? (
                  <MicOffIcon size={30} stroke="#fff" />
                ) : (
                  <MicIcon size={30} stroke="#fff" />
                )}
              </div>
            </div>
          )}

          <div className="p-statewrap" role="status" aria-live="polite">
            <div className="p-statelabel">{mutedLabel ? "Microphone muted" : meta.label}</div>
            <div className="p-statehelp">{meta.help}</div>
          </div>

          <p className="p-langnote">
            LUVE focuses on English speaking practice. Please speak English; Vietnamese or other
            languages may be misrecognized as English.
          </p>

          {error && (
            <p className="p-note" style={{ color: "var(--err-ink)", textAlign: "center" }} role="alert">
              {error}
            </p>
          )}

          {speechHint && (
            <p className="p-speech-hint" role="status" aria-live="polite">
              {speechHint}
            </p>
          )}

          {timing && hasTimings(timing) && (
            <div className="p-timing" aria-label="Realtime timings">
              {timing.readyMs != null && <span>ready {timing.readyMs} ms</span>}
              {timing.firstTokenMs != null && <span>first token {timing.firstTokenMs} ms</span>}
              {timing.responseMs != null && <span>response {timing.responseMs} ms</span>}
            </div>
          )}

          <div className="p-card p-transcript" ref={scrollRef}>
            <div className="p-transcript__label">Transcript</div>
            {transcript.length === 0 && !partial && !assistantPartial && (
              <div className="p-empty">Your conversation will appear here as you speak…</div>
            )}
            {transcript.map((t, i) => (
              <div className="p-turn" key={i}>
                <span className={"p-turn__who " + t.who}>{t.who === "ai" ? "AI" : "You"}</span>
                <div className="p-turn__text">{t.text}</div>
              </div>
            ))}
            {assistantPartial && (
              <div className="p-turn">
                <span className="p-turn__who ai">AI</span>
                <div className="p-turn__text">
                  <span className="partial">{assistantPartial}…</span>
                </div>
              </div>
            )}
            {partial && (
              <div className="p-turn">
                <span className="p-turn__who you">You</span>
                <div className="p-turn__text">
                  <span className="partial">{partial}…</span>
                </div>
              </div>
            )}
          </div>

          <div className="p-controls">
            <button
              className="btn btn--ghost"
              onClick={onMute}
              style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
            >
              {muted ? <MicOffIcon size={16} /> : <MicIcon size={16} />} {muted ? "Unmute" : "Mute"}
            </button>
            <button
              className="btn btn--ghost"
              onClick={onInterrupt}
              style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
            >
              <InterruptIcon size={16} /> Interrupt
            </button>
          </div>

          <p className="p-kbd-hint">Tip: press Space to mute or unmute the mic.</p>
        </div>
      </div>
    </div>
  );
}
