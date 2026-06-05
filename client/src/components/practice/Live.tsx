import { useEffect, useRef } from "react";
import { PHASE_META, type Phase } from "../../lib/mock";
import { MicIcon, MicOffIcon, InterruptIcon, PowerIcon } from "../icons";

export interface Turn {
  who: "ai" | "you";
  text: string;
}

interface LiveProps {
  phase: Phase;
  transcript: Turn[];
  partial: string;
  muted: boolean;
  elapsed: number;
  onMute: () => void;
  onInterrupt: () => void;
  onEnd: () => void;
}

/** Live conversation shell. Orb carries state; transcript builds turn-by-turn.
 *  All driven by scripted mock beats — no real mic/WebRTC here. */
export function Live({ phase, transcript, partial, muted, elapsed, onMute, onInterrupt, onEnd }: LiveProps) {
  const meta = PHASE_META[phase] ?? PHASE_META.listening;
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [transcript, partial]);

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

          <div className="p-card p-transcript" ref={scrollRef}>
            <div className="p-transcript__label">Transcript</div>
            {transcript.length === 0 && !partial && (
              <div className="p-empty">Your conversation will appear here as you speak…</div>
            )}
            {transcript.map((t, i) => (
              <div className="p-turn" key={i}>
                <span className={"p-turn__who " + t.who}>{t.who === "ai" ? "AI" : "You"}</span>
                <div className="p-turn__text">{t.text}</div>
              </div>
            ))}
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
        </div>
      </div>
    </div>
  );
}
