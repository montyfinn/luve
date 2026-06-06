import { useCallback, useEffect, useRef, useState } from "react";
import { Home } from "./practice/Home";
import { Live, type Turn } from "./practice/Live";
import { Ended } from "./practice/Ended";
import { Analysis } from "./practice/Analysis";
import { RecentSessions } from "./practice/RecentSessions";
import { ApiError } from "../lib/authApi";
import { createSession, type SessionHistoryItem } from "../lib/sessionApi";
import {
  getSessionGradingResult,
  getSessionGradingStatus,
  type SessionGradingResult,
  type SessionGradingStatus,
} from "../lib/gradingApi";
import { getMsUntilExpiry, isTokenExpiringSoon, loadToken } from "../lib/session";
import { createRealtimeSession, type GatewayEvent, type RealtimeSession } from "../lib/realtime";
import { deriveTimingView, type RealtimeTimingView, type RealtimeTimings } from "../lib/realtimeTimeline";
import {
  type GradingMode,
  type Phase,
  AI_LINES,
  BEATS,
  YOU_LINES,
} from "../lib/mock";

/** Flip to false to fall back to the scripted mock live flow (kept as a safety net). */
const USE_REALTIME = true;
const AUTH_EXPIRY_WARNING_MS = 2 * 60 * 1000;
const AUTH_EXPIRY_URGENT_MS = 30 * 1000;
const SHORT_SPEECH_HINT = "I didn’t catch enough speech — try a slightly longer sentence.";

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
type AnalysisStatus = "loading" | "pending" | "ready" | "insufficient" | "failed" | "unavailable" | "history";
type LoadGradingOptions = { poll?: boolean; preserveHistory?: boolean };

/**
 * Conversation shell — the third "page". Session creation, realtime connect,
 * transcript mapping, and grading status/result reads are real; the scripted
 * mock path remains only as a local safety fallback behind USE_REALTIME.
 */
export function PracticeScreen({
  userName,
  settings,
  setSettings,
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
  const [gradingResult, setGradingResult] = useState<SessionGradingResult | null>(null);
  const [gradingStatus, setGradingStatus] = useState<SessionGradingStatus | null>(null);
  const [gradingError, setGradingError] = useState<string | null>(null);
  const [historySession, setHistorySession] = useState<SessionHistoryItem | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const lastHistorySignal = useRef(historyOpenSignal);
  const gradingRequestRef = useRef(0);

  // real session-create UX
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // realtime (C7c): the live WebRTC session + any in-session error banner
  const realtimeRef = useRef<RealtimeSession | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [speechHint, setSpeechHint] = useState<string | null>(null);
  const speechHintTimer = useRef<number | null>(null);
  const [authExpiryWarning, setAuthExpiryWarning] = useState<"soon" | "urgent" | null>(null);

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
  const clearSpeechHint = useCallback(() => {
    if (speechHintTimer.current != null) {
      window.clearTimeout(speechHintTimer.current);
      speechHintTimer.current = null;
    }
    setSpeechHint(null);
  }, []);
  const showShortSpeechHint = useCallback(() => {
    if (speechHintTimer.current != null) window.clearTimeout(speechHintTimer.current);
    setSpeechHint(SHORT_SPEECH_HINT);
    speechHintTimer.current = window.setTimeout(() => {
      speechHintTimer.current = null;
      setSpeechHint(null);
    }, 7000);
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

  const loadGrading = useCallback(
    async (sessionId: string, options: LoadGradingOptions = {}) => {
      const requestId = ++gradingRequestRef.current;
      const delays = options.poll ? [0, 1600, 2400, 3600, 5200] : [0];

      if (!options.preserveHistory) setHistorySession(null);
      setGradingResult(null);
      setGradingStatus(null);
      setGradingError(null);
      setAnalysisStatus("loading");

      for (let i = 0; i < delays.length; i += 1) {
        const delay = delays[i];
        if (delay > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, delay));
          if (requestId !== gradingRequestRef.current) return;
        }

        try {
          const status = await getSessionGradingStatus(sessionId);
          if (requestId !== gradingRequestRef.current) return;
          if (status.session_id !== sessionId) {
            throw new Error("Grading status did not match the selected session.");
          }
          setGradingStatus(status);
          addLog(`GET /grading/status → ${status.status}`);

          if (status.status === "graded") {
            const result = await getSessionGradingResult(sessionId);
            if (requestId !== gradingRequestRef.current) return;
            if (result.session_id !== sessionId) {
              throw new Error("Grading result did not match the selected session.");
            }
            setGradingResult(result);
            setAnalysisStatus("ready");
            addLog("GET /grading → graded");
            return;
          }

          if (status.status === "insufficient_evidence") {
            setAnalysisStatus("insufficient");
            return;
          }

          if (status.status === "failed") {
            setAnalysisStatus("failed");
            setGradingError(status.error_code ? `Grading failed: ${status.error_code}` : "Grading failed.");
            return;
          }

          setAnalysisStatus("pending");
        } catch (e) {
          if (requestId !== gradingRequestRef.current) return;
          if (e instanceof ApiError && e.status === 401) {
            setAnalysisStatus("unavailable");
            setGradingError("Your sign-in session expired. Sign in again, then reopen this session from Past sessions.");
            addLog("GET /grading/status → 401");
            return;
          }
          setAnalysisStatus("unavailable");
          setGradingError(e instanceof Error ? e.message : "Couldn't load grading.");
          addLog("GET /grading/status → unavailable");
          return;
        }
      }
    },
    [addLog],
  );

  const handleHistorySelect = useCallback(
    (selected: SessionHistoryItem) => {
      setHistorySession(selected);
      setGradingResult(null);
      setGradingStatus(null);
      setGradingError(null);
      setAnalysisStatus("history");
      setStage("analysis");
      setHistoryOpen(false);
      addLog(`selected session history (${selected.id.slice(0, 8)}...)`);
      void loadGrading(selected.id, { preserveHistory: true });
    },
    [addLog, loadGrading],
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
            clearSpeechHint();
            if (ev.text) setTranscript((T) => [...T, { who: "you", text: ev.text }]);
            setPartial("");
            // new turn: record user-final time, reset the per-turn assistant marks
            timingsRef.current.lastUserFinalAt = now;
            timingsRef.current.assistantFirstTokenAt = undefined;
            timingsRef.current.assistantFinalAt = undefined;
            refreshTiming();
          } else {
            if (ev.text) clearSpeechHint();
            setPartial(ev.text);
          }
          break;
        case "assistant_stream":
          clearSpeechHint();
          if (timingsRef.current.assistantFirstTokenAt == null) {
            timingsRef.current.assistantFirstTokenAt = now;
            refreshTiming();
          }
          setAssistantDraft(assistantPartialRef.current + ev.delta);
          setPhase("aispeaking");
          break;
        case "assistant_final": {
          clearSpeechHint();
          const text = ev.responseText || assistantPartialRef.current;
          if (text) setTranscript((T) => [...T, { who: "ai", text }]);
          setAssistantDraft("");
          timingsRef.current.assistantFinalAt = now;
          refreshTiming();
          setPhase("listening");
          break;
        }
        case "stt_vad_ignored":
        case "stt_result_suppressed":
          showShortSpeechHint();
          break;
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
          // stt_only_final / flush_ack / barge_in_ack / assistant_audio(_meta) /
          // connected / connecting / unknown
          // → diagnostics log only; transcript unchanged.
          break;
      }
      addLog(`json_out:${ev.event}`);
    },
    [addLog, clearSpeechHint, refreshTiming, setAssistantDraft, showShortSpeechHint],
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
    setGradingResult(null);
    setGradingStatus(null);
    setGradingError(null);
    addLog(`POST /api/v1/sessions → 201 (id=${created.id.slice(0, 8)}…, status=${created.status})`);

    clearTimers();
    setTranscript([]);
    setPartial("");
    setAssistantDraft("");
    clearSpeechHint();
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
    clearSpeechHint,
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

  useEffect(() => {
    if (stage !== "live") {
      setAuthExpiryWarning(null);
      return;
    }

    const updateWarning = () => {
      if (!isTokenExpiringSoon(AUTH_EXPIRY_WARNING_MS)) {
        setAuthExpiryWarning(null);
        return;
      }
      const remainingMs = getMsUntilExpiry();
      setAuthExpiryWarning(remainingMs != null && remainingMs <= AUTH_EXPIRY_URGENT_MS ? "urgent" : "soon");
    };

    updateWarning();
    const iv = window.setInterval(updateWarning, 5000);
    return () => window.clearInterval(iv);
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
    const sessionId = activeSessionId;
    void realtimeRef.current?.disconnect("user_stop");
    realtimeRef.current = null;
    setAssistantDraft("");
    timingsRef.current.sessionEndedAt = Date.now();
    clearTimers();
    clearSpeechHint();
    addLog("END_SESSION; grading status queued");
    setStage("ended");
    after(900, () => {
      setStage("analysis");
      if (sessionId) {
        void loadGrading(sessionId, { poll: true });
      } else {
        setAnalysisStatus("unavailable");
        setGradingError("No session id was available for grading.");
      }
    });
  }, [activeSessionId, addLog, after, clearTimers, loadGrading, setAssistantDraft]);

  const practiceAgain = useCallback(() => {
    gradingRequestRef.current += 1;
    onSessionCreated(null);
    setActiveSessionId(null);
    setHistorySession(null);
    setGradingResult(null);
    setGradingStatus(null);
    setGradingError(null);
    clearSpeechHint();
    setStage("home");
  }, [clearSpeechHint, onSessionCreated]);

  // clear timers + tear down any live realtime session on unmount
  useEffect(
    () => () => {
      gradingRequestRef.current += 1;
      void realtimeRef.current?.disconnect("unmount");
      realtimeRef.current = null;
      assistantPartialRef.current = "";
      clearSpeechHint();
      clearTimers();
    },
    [clearSpeechHint, clearTimers],
  );

  const analysisSessionId = historySession?.id ?? activeSessionId;
  const refreshAnalysisGrading = analysisSessionId
    ? () => void loadGrading(analysisSessionId, { preserveHistory: Boolean(historySession) })
    : undefined;

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
        speechHint={speechHint}
        authExpiryWarning={authExpiryWarning}
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
        grading={gradingResult}
        gradingStatus={gradingStatus}
        gradingError={gradingError}
        historySession={historySession}
        onAgain={practiceAgain}
        onHistory={openHistory}
        onRefreshGrading={refreshAnalysisGrading}
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
