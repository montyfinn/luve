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

import { GATEWAY_URL } from "./config";

// --- Gateway endpoints / channel ---
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
  /** mic → offer/answer → ICE → control channel → live (session already created). */
  connect(): Promise<void>;
  /** Idempotent teardown; sends END_SESSION when live. See the cleanup contract. */
  disconnect(reason?: string): Promise<void> | void;
  /** START / FLUSH / BARGE_IN / END_SESSION — datachannel-first, HTTP fallback. */
  sendCommand(command: RealtimeCommand): Promise<void>;
  /** Toggle mic transmission; FLUSH is sent when muting (finalizes the utterance). */
  setMicMuted(muted: boolean): void;
  getState(): RealtimeLifecycleState;
}

export interface RealtimeSessionOptions {
  /** Real session_id from POST /api/v1/sessions (created before connect). */
  sessionId: string;
  sttOnly: boolean;
  ttsEnabled: boolean;
  /** Bearer token for gateway calls. */
  token: string;
  /** Defaults to GATEWAY_URL. */
  gatewayUrl?: string;
  handlers?: RealtimeSessionHandlers;
}

const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    channelCount: 1,
    sampleRate: 16000,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
  video: false,
};
const ICE_SERVERS: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
const WARMUP_TIMEOUT_MS = 12000;

/** Map a getUserMedia error to safe, user-facing copy (never logs device detail). */
export function describeMicError(error: unknown): string {
  const name =
    error && typeof error === "object" && "name" in error
      ? String((error as { name?: unknown }).name ?? "")
      : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "Microphone permission denied. Allow mic access and try again.";
  if (name === "NotFoundError" || name === "DevicesNotFoundError") return "No microphone found.";
  if (name === "NotReadableError" || name === "TrackStartError")
    return "Microphone is busy or unavailable.";
  return "Could not access the microphone.";
}

/**
 * Concrete realtime session (C7c). Owns mic + RTCPeerConnection + control
 * DataChannel + ICE against the ten_gateway. Fulfils the cleanup contract below.
 */
export function createRealtimeSession(options: RealtimeSessionOptions): RealtimeSession {
  const gatewayUrl = (options.gatewayUrl ?? GATEWAY_URL).replace(/\/+$/, "");
  const handlers = options.handlers ?? {};

  let state: RealtimeLifecycleState = "idle";
  let pc: RTCPeerConnection | null = null;
  let micStream: MediaStream | null = null;
  let controlChannel: RTCDataChannel | null = null;
  let remoteAudio: HTMLAudioElement | null = null;
  let warmupTimer: number | null = null;
  let unloadHandler: (() => void) | null = null;
  let acceptIce = false;
  let attemptId = 0;
  let micMuted = false;

  function setState(next: RealtimeLifecycleState): void {
    if (state === next) return;
    state = next;
    handlers.onStateChange?.(next);
  }

  function authHeaders(): Record<string, string> {
    return { "Content-Type": "application/json", Authorization: `Bearer ${options.token}` };
  }

  function postJson(path: string, body: unknown): Promise<Response> {
    return fetch(`${gatewayUrl}${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
  }

  // datachannel-first command send, HTTP /rtc/cmd fallback. Never logs payload text.
  async function rawSend(command: RealtimeCommand): Promise<void> {
    const payload = { session_id: options.sessionId, ...command };
    if (controlChannel && controlChannel.readyState === "open") {
      controlChannel.send(JSON.stringify(payload));
      return;
    }
    try {
      await postJson(RTC_CMD_PATH, payload);
    } catch {
      handlers.onError?.(`Command ${command.cmd} could not be delivered.`);
    }
  }

  function applyEvent(event: GatewayEvent): void {
    switch (event.event) {
      case "stt_ready":
        if (warmupTimer !== null) {
          clearTimeout(warmupTimer);
          warmupTimer = null;
        }
        micStream?.getAudioTracks().forEach((t) => {
          t.enabled = !micMuted;
        });
        setState("live");
        break;
      case "stt_ready_error":
        handlers.onError?.("Speech engine failed to start. Please end and retry.");
        setState("error");
        break;
      case "session_ended":
        setState("ended");
        break;
      case "llm_error":
        handlers.onError?.(event.message);
        break;
      default:
        break;
    }
  }

  function bindChannel(channel: RTCDataChannel): void {
    channel.onopen = () => {
      if (channel.label === CONTROL_CHANNEL_LABEL) {
        void rawSend({ cmd: "START", stt_only: options.sttOnly, tts_enabled: options.ttsEnabled });
      }
    };
    channel.onmessage = (ev: MessageEvent) => {
      const consume = (text: string) => {
        const event = parseGatewayEvent(text);
        applyEvent(event);
        handlers.onEvent?.(event);
      };
      if (typeof ev.data === "string") consume(ev.data);
      else if (ev.data instanceof Blob) void ev.data.text().then(consume);
    };
  }

  function teardown(): void {
    acceptIce = false;
    attemptId += 1;
    if (warmupTimer !== null) {
      clearTimeout(warmupTimer);
      warmupTimer = null;
    }
    if (unloadHandler) {
      window.removeEventListener("pagehide", unloadHandler);
      window.removeEventListener("beforeunload", unloadHandler);
      unloadHandler = null;
    }
    if (controlChannel) {
      try {
        controlChannel.close();
      } catch {
        /* ignore */
      }
      controlChannel = null;
    }
    if (pc) {
      pc.getSenders().forEach((s) => {
        try {
          s.track?.stop();
        } catch {
          /* ignore */
        }
      });
      try {
        pc.close();
      } catch {
        /* ignore */
      }
      pc = null;
    }
    if (micStream) {
      micStream.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* ignore */
        }
      });
      micStream = null;
    }
    if (remoteAudio) {
      try {
        remoteAudio.pause();
      } catch {
        /* ignore */
      }
      remoteAudio.srcObject = null;
      remoteAudio = null;
    }
  }

  function failConnect(message: string, cause?: unknown): never {
    handlers.onError?.(message);
    teardown();
    setState("error");
    throw cause instanceof Error ? cause : new Error(message);
  }

  async function connect(): Promise<void> {
    if (pc) return; // idempotent guard against double Start
    attemptId += 1;
    const myAttempt = attemptId;
    acceptIce = true;
    setState("connecting");

    // Microphone — requested ONLY here (i.e. only after an explicit Start click).
    try {
      micStream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
    } catch (error) {
      micStream = null;
      failConnect(describeMicError(error), error);
    }
    const stream = micStream as MediaStream;

    const peer = new RTCPeerConnection({ iceServers: ICE_SERVERS });
    pc = peer;

    // Mute tracks during DTLS/ICE warmup; re-enabled on stt_ready.
    stream.getAudioTracks().forEach((t) => {
      t.enabled = false;
      peer.addTrack(t, stream);
    });

    peer.ontrack = (ev: RTCTrackEvent) => {
      const [incoming] = ev.streams;
      if (!incoming) return;
      if (!remoteAudio) {
        remoteAudio = document.createElement("audio");
        remoteAudio.autoplay = true;
      }
      remoteAudio.srcObject = incoming;
      void remoteAudio.play().catch(() => {
        /* autoplay may be blocked until interaction; harmless */
      });
    };

    peer.onicecandidate = (ev: RTCPeerConnectionIceEvent) => {
      if (!ev.candidate) return;
      if (myAttempt !== attemptId || !acceptIce || peer !== pc) return;
      if (peer.connectionState === "closed" || peer.signalingState === "closed") return;
      const candidate = ev.candidate.toJSON();
      void postJson(RTC_ICE_PATH, { session_id: options.sessionId, candidate }).catch(() => {
        handlers.onError?.("A network candidate could not be sent.");
      });
    };

    peer.ondatachannel = (ev: RTCDataChannelEvent) => bindChannel(ev.channel);

    controlChannel = peer.createDataChannel(CONTROL_CHANNEL_LABEL, { ordered: true });
    bindChannel(controlChannel);

    const offer = await peer.createOffer({ offerToReceiveAudio: true });
    await peer.setLocalDescription(offer);

    let response: Response;
    try {
      response = await postJson(RTC_OFFER_PATH, {
        type: offer.type,
        sdp: offer.sdp,
        session_id: options.sessionId,
        stt_only: options.sttOnly,
        tts_enabled: options.ttsEnabled,
        extension: "luve_core_media_extension",
        ports: { audio_in: "audio_in", audio_out: "audio_out", json_out: "json_out", log_out: "log_out" },
      });
    } catch (error) {
      failConnect("Couldn't reach the speech gateway.", error);
    }
    if (!response.ok) {
      failConnect(`Speech gateway error (HTTP ${response.status}).`);
    }

    const envelope = (await response.json()) as {
      answer?: RTCSessionDescriptionInit;
      candidates?: RTCIceCandidateInit[];
      session_id?: string;
    };
    if (peer !== pc) return; // torn down while awaiting
    const answer = (envelope.answer ?? envelope) as RTCSessionDescriptionInit;
    await peer.setRemoteDescription(answer);
    if (Array.isArray(envelope.candidates)) {
      for (const candidate of envelope.candidates) {
        try {
          await peer.addIceCandidate(candidate);
        } catch {
          /* ignore a single bad candidate */
        }
      }
    }

    warmupTimer = window.setTimeout(() => {
      if (state === "connecting") handlers.onError?.("Speech engine is still warming up…");
    }, WARMUP_TIMEOUT_MS);

    // On tab close while active, best-effort END_SESSION + full teardown.
    unloadHandler = () => {
      if ((state === "live" || state === "connecting") && options.token) {
        try {
          fetch(`${gatewayUrl}${RTC_CMD_PATH}`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ session_id: options.sessionId, cmd: "END_SESSION", source: "page_unload" }),
            keepalive: true,
          });
        } catch {
          /* ignore */
        }
      }
      teardown();
    };
    window.addEventListener("pagehide", unloadHandler);
    window.addEventListener("beforeunload", unloadHandler);
  }

  async function disconnect(reason?: string): Promise<void> {
    if (state === "idle" || state === "ending" || state === "ended") {
      teardown(); // clean any residue; idempotent
      if (state !== "ended") setState("ended");
      return;
    }
    setState("ending");
    try {
      await rawSend({ cmd: "END_SESSION", source: reason ?? "user_stop" });
    } catch {
      /* best-effort */
    }
    teardown();
    setState("ended");
  }

  async function sendCommand(command: RealtimeCommand): Promise<void> {
    await rawSend(command);
  }

  function setMicMuted(muted: boolean): void {
    micMuted = muted;
    micStream?.getAudioTracks().forEach((t) => {
      t.enabled = !muted;
    });
    if (muted) void rawSend({ cmd: "FLUSH" });
  }

  return { connect, disconnect, sendCommand, setMicMuted, getState: () => state };
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
