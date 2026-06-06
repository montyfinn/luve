import { useCallback, useEffect, useRef, useState } from "react";
import { Home } from "./practice/Home";
import { Live, type Turn } from "./practice/Live";
import { Ended } from "./practice/Ended";
import { Analysis } from "./practice/Analysis";
import { RecentSessions } from "./practice/RecentSessions";
import { createSession, type SessionHistoryItem } from "../lib/sessionApi";
import { loadToken } from "../lib/session";
import { createRealtimeSession, type GatewayEvent, type RealtimeSession } from "../lib/realtime";
import { deriveTimingView, type RealtimeTimingView, type RealtimeTimings } from "../lib/realtimeTimeline";
import {
  AI_LINES,
  BEATS,
  YOU_LINES,
  buildCurrentSession,
  type GradingMode,
  type Phase,
  type SessionResult,
} from "../lib/mock";

/** Flip to false to fall back to the scripted mock live flow (kept as a safety net). */
const USE_REALTIME = true;

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
  /** lifts the real session_id to App (for the diagnostics drawer) */
  onSessionCreated: (sessionId: string | null) => void;
  /** monotonically increasing signal from the top-bar History button */
  historyOpenSignal: number;
  /** lets the app show the top-bar History button only on supported stages */
  onHistoryAvailabilityChange: (available: boolean) => void;
}

type Stage = "home" | "live" | "ended" | "analysis";
type AnalysisStatus = "loading" | "ready" | "insufficient" | "history";

/**
 * Conversation shell — the third "page". Session CREATION is now REAL
 * (POST /api/v1/sessions with the bearer token); once created, the live
 * conversation, transcript, and grading remain SCRIPTED MOCK. No microphone,
 * WebRTC, or /rtc calls here.
 */
export function PracticeScreen({
  userName,
  settings,
  setSettings,
  gradingMode,
  addLog,
  onSessionCreated,
  historyOpenSignal,
  onHistoryAvailabilityChange,
}: PracticeScreenProps) {
  const [stage, setStage] = useState<Stage>("home");
  const [phase, setPhase] = useState<Phase>("connecting");
  const [transcript, setTranscript] = useState<Turn[]>([]);
  const [partial, setPartial] = useState("");
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>("loading");
  const [session, setSession] = useState<SessionResult | null>(null);
  const [historySession, setHistorySession] = useState<SessionHistoryItem | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const lastHistorySignal = useRef(historyOpenSignal);

  // real session-create UX
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // realtime (C7c): the live WebRTC session + any in-session error banner
  const realtimeRef = useRef<RealtimeSession | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);

  // C7d: streaming assistant draft + lightweight client-side timing view
  const [assistantPartial, setAssistantPartial] = useState("");
  const assistantPartialRef = useRef("");
  const setAssistantDraft = useCallback((next: string) => {
    assistantPartialRef.current = next;
    setAssistantPartial(next);
  }, []);
  const timingsRef = useRef<RealtimeTimings>({});
  const [timingView, setTimingView] = useState<RealtimeTimingView | null>(null);
  const refreshTiming = useCallback(() => setTimingView(deriveTimingView({ ...timingsRef.current })), []);

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

  const historyAvailable = stage === "home" || stage === "analysis";

  useEffect(() => {
    onHistoryAvailabilityChange(historyAvailable);
    if (!historyAvailable) setHistoryOpen(false);
    return () => onHistoryAvailabilityChange(false);
  }, [historyAvailable, onHistoryAvailabilityChange]);

  const openHistory = useCallback(() => {
    if (!historyAvailable) return;
    setHistoryOpen(true);
  }, [historyAvailable]);

  useEffect(() => {
    if (historyOpenSignal === lastHistorySignal.current) return;
    lastHistorySignal.current = historyOpenSignal;
    openHistory();
  }, [historyOpenSignal, openHistory]);

  const handleHistorySelect = useCallback(
    (selected: SessionHistoryItem) => {
      setHistorySession(selected);
      setSession(null);
      setAnalysisStatus("history");
      setStage("analysis");
      setHistoryOpen(false);
      addLog(`selected session history summary (${selected.id.slice(0, 8)}...)`);
    },
    [addLog],
  );

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
        addLog('STT final: "' + YOU_LINES[b.you!].slice(0, 28) + '…"  [mock]');
        after(b.dur, () => runBeat(i + 1));
        return;
      }
      setPhase(b.phase);
      if (b.phase === "aispeaking") {
        setTranscript((T) => [...T, { who: "ai", text: AI_LINES[b.ai!] }]);
        addLog("assistant_stream → TTS chunk  [mock]");
      }
      if (b.phase === "thinking") addLog("LLM thinking…  [mock]");
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

  // C7d event → transcript/status/timing mapping. Logs the event TYPE only —
  // never full transcript text or audio. Unknown/diagnostic events fall through
  // to the log and leave the transcript untouched (UI stays usable).
  const applyRealtimeEvent = useCallback(
    (ev: GatewayEvent) => {
      const now = Date.now();
      switch (ev.event) {
        case "subtitle":
        case "stt_result":
          if (ev.is_final) {
            if (ev.text) setTranscript((T) => [...T, { who: "you", text: ev.text }]);
            setPartial("");
            // new turn: record user-final time, reset the per-turn assistant marks
            timingsRef.current.lastUserFinalAt = now;
            timingsRef.current.assistantFirstTokenAt = undefined;
            timingsRef.current.assistantFinalAt = undefined;
            refreshTiming();
          } else {
            setPartial(ev.text);
          }
          break;
        case "assistant_stream":
          if (timingsRef.current.assistantFirstTokenAt == null) {
            timingsRef.current.assistantFirstTokenAt = now;
            refreshTiming();
          }
          setAssistantDraft(assistantPartialRef.current + ev.delta);
          setPhase("aispeaking");
          break;
        case "assistant_final": {
          const text = ev.responseText || assistantPartialRef.current;
          if (text) setTranscript((T) => [...T, { who: "ai", text }]);
          setAssistantDraft("");
          timingsRef.current.assistantFinalAt = now;
          refreshTiming();
          setPhase("listening");
          break;
        }
        case "assistant_audio_aborted":
        case "assistant_generation_aborted": {
          // keep whatever streamed so far visible, then stop the draft
          const text = assistantPartialRef.current;
          if (text) setTranscript((T) => [...T, { who: "ai", text }]);
          setAssistantDraft("");
          setPhase("listening");
          break;
        }
        case "ten_started":
          setPhase("connecting");
          break;
        case "stt_ready":
          if (timingsRef.current.sttReadyAt == null) {
            timingsRef.current.sttReadyAt = now;
            refreshTiming();
          }
          setPhase("listening");
          break;
        case "stt_ready_error":
          setLiveError("Speech engine failed to start. End the session and try again.");
          break;
        case "llm_error":
          setLiveError(ev.message);
          break;
        case "session_ended":
          timingsRef.current.sessionEndedAt = now;
          refreshTiming();
          break;
        default:
          // stt_result_suppressed / stt_vad_ignored / stt_only_final / flush_ack /
          // barge_in_ack / assistant_audio(_meta) / connected / connecting / unknown
          // → diagnostics log only; transcript unchanged.
          break;
      }
      addLog(`json_out:${ev.event}`);
    },
    [addLog, refreshTiming, setAssistantDraft],
  );

  // REAL session create + REAL realtime connect (mock kept behind USE_REALTIME).
  const startSession = useCallback(async () => {
    if (starting) return;
    setStarting(true);
    setStartError(null);
    timingsRef.current = { startClickAt: Date.now() };
    setTimingView(null);

    let created;
    try {
      created = await createSession({ sttOnly: settings.sttOnly, muteTts: settings.muteTts });
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Couldn't start the session.");
      setStarting(false);
      return;
    }

    onSessionCreated(created.id);
    setActiveSessionId(created.id);
    setHistorySession(null);
    setSession(null);
    addLog(`POST /api/v1/sessions → 201 (id=${created.id.slice(0, 8)}…, status=${created.status})`);

    clearTimers();
    setTranscript([]);
    setPartial("");
    setAssistantDraft("");
    setMuted(false);
    setElapsed(0);
    setLiveError(null);
    setPhase("connecting");
    setStage("live");
    setStarting(false);
    timingsRef.current.sessionCreatedAt = Date.now();

    if (!USE_REALTIME) {
      addLog("RTC offer + transcript are mock in this build");
      after(1300, () => {
        addLog("mock RTC connected");
        runBeat(0);
      });
      return;
    }

    const token = loadToken();
    if (!token) {
      setStartError("Please sign in again before starting a session.");
      setStage("home");
      return;
    }

    const session = createRealtimeSession({
      sessionId: created.id,
      sttOnly: settings.sttOnly,
      ttsEnabled: !settings.sttOnly && !settings.muteTts,
      token,
      handlers: {
        onStateChange: (s) => {
          if (s === "connecting") setPhase("connecting");
          else if (s === "live") {
            setPhase("listening");
            if (timingsRef.current.sttReadyAt == null) {
              timingsRef.current.sttReadyAt = Date.now();
              refreshTiming();
            }
          }
        },
        onEvent: applyRealtimeEvent,
        onError: setLiveError,
      },
    });
    realtimeRef.current = session;
    addLog("POST /rtc/offer → connecting…");

    try {
      await session.connect();
      timingsRef.current.offerAnsweredAt = Date.now();
      refreshTiming();
    } catch {
      // onError already surfaced a friendly message; return to home.
      realtimeRef.current = null;
      setStage("home");
    }
  }, [
    starting,
    settings,
    onSessionCreated,
    addLog,
    after,
    clearTimers,
    runBeat,
    applyRealtimeEvent,
    refreshTiming,
    setAssistantDraft,
  ]);

  // elapsed timer while live
  useEffect(() => {
    if (stage !== "live") return;
    const iv = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(iv);
  }, [stage]);

  const handleInterrupt = useCallback(() => {
    if (phase === "aispeaking" || phase === "thinking") {
      void realtimeRef.current?.sendCommand({ cmd: "BARGE_IN", source: "button" });
      addLog("BARGE_IN");
    }
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
      const next = !m;
      realtimeRef.current?.setMicMuted(next);
      addLog(next ? "FLUSH (mute)" : "mic unmuted");
      return next;
    });
  }, [addLog]);

  const endSession = useCallback(() => {
    void realtimeRef.current?.disconnect("user_stop");
    realtimeRef.current = null;
    setAssistantDraft("");
    timingsRef.current.sessionEndedAt = Date.now();
    clearTimers();
    addLog("END_SESSION; grading queued  [mock grading]");
    setStage("ended");
    after(1600, () => {
      setAnalysisStatus("loading");
      setStage("analysis");
      addLog("GET /grading/status → processing  [mock]");
      after(2400, () => {
        addLog("GET /grading/status → " + gradingMode + "; GET /grading  [mock]");
        setHistorySession(null);
        if (gradingMode === "insufficient") {
          setAnalysisStatus("insufficient");
        } else {
          setSession(buildCurrentSession(gradingMode));
          setAnalysisStatus("ready");
        }
      });
    });
  }, [addLog, after, clearTimers, gradingMode, setAssistantDraft]);

  const practiceAgain = useCallback(() => {
    onSessionCreated(null);
    setActiveSessionId(null);
    setHistorySession(null);
    setStage("home");
  }, [onSessionCreated]);

  // clear timers + tear down any live realtime session on unmount
  useEffect(
    () => () => {
      void realtimeRef.current?.disconnect("unmount");
      realtimeRef.current = null;
      assistantPartialRef.current = "";
      clearTimers();
    },
    [clearTimers],
  );

  if (stage === "home") {
    return (
      <>
        <Home
          userName={userName}
          onStart={startSession}
          starting={starting}
          startError={startError}
          settings={settings}
          setSettings={setSettings}
        />
        <RecentSessions
          open={historyOpen}
          currentId={activeSessionId}
          selectedId={historySession?.id ?? null}
          onClose={() => setHistoryOpen(false)}
          onSelect={handleHistorySelect}
          onLog={addLog}
        />
      </>
    );
  }
  if (stage === "live") {
    return (
      <Live
        phase={phase}
        transcript={transcript}
        partial={partial}
        assistantPartial={assistantPartial}
        timing={timingView}
        muted={muted}
        elapsed={elapsed}
        error={liveError}
        onMute={handleMute}
        onInterrupt={handleInterrupt}
        onEnd={endSession}
      />
    );
  }
  if (stage === "ended") {
    return <Ended />;
  }
  return (
    <>
      <Analysis
        status={analysisStatus}
        session={session}
        historySession={historySession}
        onAgain={practiceAgain}
        onHistory={openHistory}
      />
      <RecentSessions
        open={historyOpen}
        currentId={activeSessionId}
        selectedId={historySession?.id ?? null}
        onClose={() => setHistoryOpen(false)}
        onSelect={handleHistorySelect}
        onLog={addLog}
      />
    </>
  );
}
