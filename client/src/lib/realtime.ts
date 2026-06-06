/**
 * Realtime session contract for the LUVE speaking pipeline (ten_gateway).
 *
 * C7b SCOPE — types + a pure event parser + the lifecycle/cleanup CONTRACT only.
 * There is intentionally NO microphone access, NO RTCPeerConnection, NO
 * DataChannel, and NO /rtc/* network call in this file. Those land in C7c–C7e,
 * implemented behind the `RealtimeSession` interface and the cleanup contract
 * documented at the bottom.
 *
 * The contract is reverse-engineered from the proven static control-center flow
 * (services/core-api/src/static/index.html) — see the C7a audit. Gateway base
 * URL + endpoints live in ./config (GATEWAY_URL) and the path constants below;
 * they are referenced by the C7c implementation, not contacted here.
 */

// --- Gateway endpoints / channel (used by the C7c+ implementation) ---
export const RTC_OFFER_PATH = "/rtc/offer";
export const RTC_ICE_PATH = "/rtc/ice";
export const RTC_CMD_PATH = "/rtc/cmd";
/** Ordered control DataChannel the client opens; START is sent on its `open`. */
export const CONTROL_CHANNEL_LABEL = "luve-control";

/** Max characters for any log/preview of model/user text (never full transcript). */
export const PREVIEW_MAX = 120;

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

/**
 * Client-side realtime lifecycle:
 *  idle       — nothing running
 *  creating   — POST /api/v1/sessions (core_api) to obtain a session_id
 *  connecting — mic + offer/answer + ICE + control-channel warmup (until stt_ready)
 *  live       — stt_ready received; the learner can speak
 *  ending     — END_SESSION sent, tearing the peer connection down
 *  ended      — session_ended / clean teardown complete
 *  error      — unrecoverable (mic denied, gateway/offer failure, stt_ready_error)
 */
export type RealtimeLifecycleState =
  | "idle"
  | "creating"
  | "connecting"
  | "live"
  | "ending"
  | "ended"
  | "error";

// ---------------------------------------------------------------------------
// Outbound commands (datachannel-first, HTTP /rtc/cmd fallback in the impl)
// ---------------------------------------------------------------------------

export interface StartCommand {
  cmd: "START";
  stt_only: boolean;
  tts_enabled: boolean;
}
export interface FlushCommand {
  cmd: "FLUSH";
}
export interface BargeInCommand {
  cmd: "BARGE_IN";
  source: string;
}
export interface EndSessionCommand {
  cmd: "END_SESSION";
  source: string;
}

export type RealtimeCommand = StartCommand | FlushCommand | BargeInCommand | EndSessionCommand;
export type RealtimeCommandType = RealtimeCommand["cmd"];

// ---------------------------------------------------------------------------
// Inbound gateway events (parsed from the control DataChannel JSON)
// ---------------------------------------------------------------------------

interface BaseEvent {
  /** Present on most gateway messages; null when absent. */
  session_id: string | null;
}

/** Transcript hypotheses: partial (is_final=false) and final (is_final=true). */
export interface SttResultEvent extends BaseEvent {
  event: "subtitle" | "stt_result";
  is_final: boolean;
  /** Extracted from `stt.raw_text`; capped previews are the caller's job. */
  text: string;
  trigger: string | null;
}

/** STT outputs that were dropped/ignored upstream — no transcript text surfaced. */
export interface SttDroppedEvent extends BaseEvent {
  event: "stt_result_suppressed" | "stt_vad_ignored" | "stt_only_final";
}

export interface AssistantStreamEvent extends BaseEvent {
  event: "assistant_stream";
  delta: string;
  source?: string;
}

export interface AssistantFinalEvent extends BaseEvent {
  event: "assistant_final";
  responseText: string;
  pedagogicalFeedback?: string;
  source?: string;
}

/**
 * TTS PCM chunk. NOTE: the raw `audio_b64` payload is deliberately NOT retained
 * — only its presence is reported, so audio never leaks into logs/state here.
 */
export interface AssistantAudioEvent extends BaseEvent {
  event: "assistant_audio";
  sampleRate: number;
  channels: number;
  hasAudio: boolean;
}

export interface SttReadyErrorEvent extends BaseEvent {
  event: "stt_ready_error";
  reason?: string;
  detail: string | null;
}

export interface PedagogicalFeedbackEvent extends BaseEvent {
  event: "pedagogical_feedback";
  feedback: string;
}

export interface LlmErrorEvent extends BaseEvent {
  event: "llm_error";
  message: string;
}

/**
 * Lifecycle / ack / abort signals with no consumer-relevant payload.
 * `connected`/`connecting` mirror RTCPeerConnection connection-state transitions
 * (surfaced as signals), not JSON `event` payloads — the rest are gateway events.
 */
export type SimpleEventType =
  | "ten_started"
  | "stt_ready"
  | "session_ended"
  | "flush_ack"
  | "barge_in_ack"
  | "assistant_audio_meta"
  | "assistant_audio_aborted"
  | "assistant_generation_aborted"
  | "connected"
  | "connecting";

export interface SimpleGatewayEvent extends BaseEvent {
  event: SimpleEventType;
}

/** Fallback for missing/unrecognized event types — parser never throws. */
export interface UnknownGatewayEvent extends BaseEvent {
  event: "unknown";
  /** The original (lowercased) `event` string, if any. */
  rawType: string;
}

export type GatewayEvent =
  | SttResultEvent
  | SttDroppedEvent
  | AssistantStreamEvent
  | AssistantFinalEvent
  | AssistantAudioEvent
  | SttReadyErrorEvent
  | PedagogicalFeedbackEvent
  | LlmErrorEvent
  | SimpleGatewayEvent
  | UnknownGatewayEvent;

export type GatewayEventType = GatewayEvent["event"];

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
function optString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}
function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/** Collapse whitespace and cap to PREVIEW_MAX — safe for logs/telemetry. */
export function previewText(text: string): string {
  const cleaned = (text ?? "").replace(/\s+/g, " ").trim();
  return cleaned.length > PREVIEW_MAX ? `${cleaned.slice(0, PREVIEW_MAX)}…` : cleaned;
}

/**
 * Parse a control-channel message into a typed `GatewayEvent`.
 *
 * Accepts an already-parsed object or a JSON string. NEVER throws: malformed,
 * non-object, or unknown-`event` input returns an `unknown` event. Audio bytes
 * (`audio_b64`) are never retained.
 */
export function parseGatewayEvent(input: unknown): GatewayEvent {
  let data: Record<string, unknown>;
  if (typeof input === "string") {
    try {
      data = JSON.parse(input) as Record<string, unknown>;
    } catch {
      return { event: "unknown", rawType: "", session_id: null };
    }
  } else if (input !== null && typeof input === "object") {
    data = input as Record<string, unknown>;
  } else {
    return { event: "unknown", rawType: "", session_id: null };
  }

  if (!data || typeof data !== "object") {
    return { event: "unknown", rawType: "", session_id: null };
  }

  const rawType = asString(data.event).toLowerCase();
  const session_id = typeof data.session_id === "string" ? data.session_id : null;

  switch (rawType) {
    case "subtitle":
    case "stt_result": {
      const stt =
        data.stt !== null && typeof data.stt === "object" ? (data.stt as Record<string, unknown>) : {};
      return {
        event: rawType,
        session_id,
        is_final: Boolean(data.is_final),
        text: asString(stt.raw_text),
        trigger: typeof data.trigger === "string" ? data.trigger : null,
      };
    }
    case "assistant_stream":
      return { event: "assistant_stream", session_id, delta: asString(data.delta), source: optString(data.source) };
    case "assistant_final":
      return {
        event: "assistant_final",
        session_id,
        responseText: asString(data.response_text),
        pedagogicalFeedback: optString(data.pedagogical_feedback),
        source: optString(data.source),
      };
    case "assistant_audio":
      return {
        event: "assistant_audio",
        session_id,
        sampleRate: asNumber(data.sample_rate, 16000),
        channels: asNumber(data.channels, 1),
        hasAudio: typeof data.audio_b64 === "string" && data.audio_b64.length > 0,
      };
    case "stt_ready_error":
      return {
        event: "stt_ready_error",
        session_id,
        reason: optString(data.reason),
        detail: typeof data.detail === "string" ? data.detail : null,
      };
    case "pedagogical_feedback":
      return { event: "pedagogical_feedback", session_id, feedback: asString(data.feedback ?? data.text) };
    case "llm_error":
      return { event: "llm_error", session_id, message: asString(data.message) || "LLM service unavailable" };
    case "stt_result_suppressed":
    case "stt_vad_ignored":
    case "stt_only_final":
      return { event: rawType, session_id };
    case "ten_started":
    case "stt_ready":
    case "session_ended":
    case "flush_ack":
    case "barge_in_ack":
    case "assistant_audio_meta":
    case "assistant_audio_aborted":
    case "assistant_generation_aborted":
    case "connected":
    case "connecting":
      return { event: rawType, session_id };
    default:
      return { event: "unknown", rawType, session_id };
  }
}

// ---------------------------------------------------------------------------
// Session interface (implemented in C7c–C7e)
// ---------------------------------------------------------------------------

/** Callbacks the concrete session will invoke. Defined now to fix the contract. */
export interface RealtimeSessionHandlers {
  onStateChange?: (state: RealtimeLifecycleState) => void;
  onEvent?: (event: GatewayEvent) => void;
  /** Safe, code-level errors only — never raw audio/transcript. */
  onError?: (message: string) => void;
}

export interface RealtimeSession {
  /** Create session (if needed) → mic → offer/answer → control channel → live. */
  connect(): Promise<void>;
  /** Idempotent teardown; sends END_SESSION when live. See the cleanup contract. */
  disconnect(reason?: string): Promise<void> | void;
  /** START / FLUSH / BARGE_IN / END_SESSION — datachannel-first, HTTP fallback. */
  sendCommand(command: RealtimeCommand): Promise<void>;
  getState(): RealtimeLifecycleState;
}

/**
 * Placeholder factory — the real WebRTC implementation lands in C7c.
 * It performs NO media/network work; calling connect()/sendCommand() rejects so
 * accidental early wiring fails loudly rather than silently doing nothing.
 */
export function createRealtimeSession(): RealtimeSession {
  let state: RealtimeLifecycleState = "idle";
  const notImplemented = () => Promise.reject(new Error("RealtimeSession not implemented yet (C7c)"));
  return {
    connect: notImplemented,
    sendCommand: notImplemented,
    disconnect: () => {
      state = "idle";
    },
    getState: () => state,
  };
}

// ===========================================================================
// CLEANUP CONTRACT (binding on the C7c–C7e implementation)
//
// On disconnect()/teardown/unmount/error, the implementation MUST:
//   1. Stop every microphone track (track.stop()) and release the MediaStream.
//   2. Close the control DataChannel (and any gateway-pushed channel).
//   3. Close the RTCPeerConnection and stop all senders' tracks.
//   4. Reject stale ICE: guard by an attempt id + session id + peer identity,
//      and stop accepting candidates once tearing down.
//   5. On pagehide/beforeunload while live, send END_SESSION via a keepalive
//      fetch to /rtc/cmd before closing.
//   6. Be idempotent — duplicate stop/end must not double-send or throw.
//   7. NEVER leak full audio (audio_b64) or full transcript into logs/state;
//      use previewText() (capped at PREVIEW_MAX) for any text telemetry.
// ===========================================================================
