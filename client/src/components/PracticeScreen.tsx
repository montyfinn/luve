import { useCallback, useEffect, useRef, useState } from "react";
import { Home } from "./practice/Home";
import { Live, type Turn } from "./practice/Live";
import { Ended } from "./practice/Ended";
import { Analysis } from "./practice/Analysis";
import {
  AI_LINES,
  BEATS,
  YOU_LINES,
  buildCurrentSession,
  type GradingMode,
  type Phase,
  type SessionResult,
} from "../lib/mock";

interface Settings {
  sttOnly: boolean;
  muteTts: boolean;
}

interface PracticeScreenProps {
  userName: string;
  settings: Settings;
  setSettings: (s: Settings) => void;
  gradingMode: GradingMode; // from diagnostics "Demo controls"
  addLog: (m: string) => void;
}

type Stage = "home" | "live" | "ended" | "analysis";
type AnalysisStatus = "loading" | "ready" | "insufficient";

/**
 * Conversation shell — the third "page". Manages an internal stage machine
 * (home -> live -> ended -> analysis) driven entirely by SCRIPTED MOCK BEATS.
 * No microphone, WebRTC, or grading API — the "API" strings are log-only.
 */
export function PracticeScreen({ userName, settings, setSettings, gradingMode, addLog }: PracticeScreenProps) {
  const [stage, setStage] = useState<Stage>("home");
  const [phase, setPhase] = useState<Phase>("connecting");
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [partial, setPartial] = useState("");
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>("loading");
  const [session, setSession] = useState<SessionResult | null>(null);

  const timers = useRef<number[]>([]);
  const after = useCallback((ms: number, fn: () => void) => {
    const t = window.setTimeout(fn, ms);
    timers.current.push(t);
    return t;
  }, []);
  const clearTimers = useCallback(() => {
    timers.current.forEach((t) => clearTimeout(t));
    timers.current = [];
  }, []);

  const runBeat = useCallback(
    (i: number) => {
      if (i >= BEATS.length) {
        setPhase("listening");
        return;
      }
      const b = BEATS[i];
      if (b.phase === "commit") {
        setPartial("");
        setTranscript((T) => [...T, { who: "you", text: YOU_LINES[b.you!] }]);
        addLog('STT final: "' + YOU_LINES[b.you!].slice(0, 28) + '…"');
        after(b.dur, () => runBeat(i + 1));
        return;
      }
      setPhase(b.phase);
      if (b.phase === "aispeaking") {
        setTranscript((T) => [...T, { who: "ai", text: AI_LINES[b.ai!] }]);
        addLog("assistant_stream → TTS chunk");
      }
      if (b.phase === "thinking") addLog("LLM thinking…");
      if (b.phase === "speaking") {
        const words = YOU_LINES[b.you!].split(" ");
        setPartial("");
        const step = Math.max(120, Math.floor(b.dur / (words.length + 1)));
        words.forEach((_, wi) => after(step * (wi + 1), () => setPartial(words.slice(0, wi + 1).join(" "))));
      }
      after(b.dur, () => runBeat(i + 1));
    },
    [addLog, after],
  );

  const startSession = useCallback(() => {
    clearTimers();
    setTranscript([]);
    setPartial("");
    setMuted(false);
    setElapsed(0);
    setPhase("connecting");
    setStage("live");
    addLog("POST /sessions → ready; POST /rtc/offer (SDP)  [mock]");
    after(1300, () => {
      addLog("RTC connected  [mock]");
      runBeat(0);
    });
  }, [addLog, after, clearTimers, runBeat]);

  // elapsed timer while live
  useEffect(() => {
    if (stage !== "live") return;
    const iv = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(iv);
  }, [stage]);

  const handleInterrupt = useCallback(() => {
    if (phase === "aispeaking" || phase === "thinking") addLog("POST /rtc/cmd BARGE_IN  [mock]");
  }, [phase, addLog]);

  // spacebar = barge-in while live
  useEffect(() => {
    if (stage !== "live") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        handleInterrupt();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage, handleInterrupt]);

  const handleMute = useCallback(() => {
    setMuted((m) => {
      addLog(!m ? "POST /rtc/cmd FLUSH (mute)  [mock]" : "mic unmuted  [mock]");
      return !m;
    });
  }, [addLog]);

  const endSession = useCallback(() => {
    clearTimers();
    addLog("POST /rtc/cmd END_SESSION; grading queued  [mock]");
    setStage("ended");
    after(1600, () => {
      setAnalysisStatus("loading");
      setStage("analysis");
      addLog("GET /grading/status → processing  [mock]");
      after(2400, () => {
        addLog("GET /grading/status → " + gradingMode + "; GET /grading  [mock]");
        if (gradingMode === "insufficient") {
          setAnalysisStatus("insufficient");
        } else {
          setSession(buildCurrentSession(gradingMode));
          setAnalysisStatus("ready");
        }
      });
    });
  }, [addLog, after, clearTimers, gradingMode]);

  const practiceAgain = useCallback(() => setStage("home"), []);

  // clear timers on unmount
  useEffect(() => () => clearTimers(), [clearTimers]);

  if (stage === "home") {
    return <Home userName={userName} onStart={startSession} settings={settings} setSettings={setSettings} />;
  }
  if (stage === "live") {
    return (
      <Live
        phase={phase}
        transcript={transcript}
        partial={partial}
        muted={muted}
        elapsed={elapsed}
        onMute={handleMute}
        onInterrupt={handleInterrupt}
        onEnd={endSession}
      />
    );
  }
  if (stage === "ended") {
    return <Ended />;
  }
  return <Analysis status={analysisStatus} session={session} onAgain={practiceAgain} />;
}
