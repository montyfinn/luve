/**
 * Lightweight, pure client-side timing model for a realtime practice session.
 * Records a handful of wall-clock marks and derives user-meaningful latencies.
 * No side effects, no logging — the caller decides what to display.
 *
 * NOTE: these are CLIENT-OBSERVED times (event arrival), not server inference
 * times. True STT inference latency lives in gateway logs; here we surface what
 * the browser can derive (connect/ready and the perceived response round-trip).
 */
export interface RealtimeTimings {
  startClickAt?: number;
  sessionCreatedAt?: number;
  offerAnsweredAt?: number;
  sttReadyAt?: number;
  lastUserFinalAt?: number;
  assistantFirstTokenAt?: number;
  assistantFinalAt?: number;
  sessionEndedAt?: number;
}

export interface RealtimeTimingView {
  /** Start click → SDP answer received. */
  offerMs: number | null;
  /** Start click → "ready, speak now" (stt_ready). */
  readyMs: number | null;
  /** Your last final → assistant's first streamed token. */
  firstTokenMs: number | null;
  /** Your last final → assistant final (perceived round-trip). */
  responseMs: number | null;
}

function delta(a?: number, b?: number): number | null {
  return a != null && b != null && b >= a ? Math.round(b - a) : null;
}

export function deriveTimingView(t: RealtimeTimings): RealtimeTimingView {
  return {
    offerMs: delta(t.startClickAt, t.offerAnsweredAt),
    readyMs: delta(t.startClickAt, t.sttReadyAt),
    firstTokenMs: delta(t.lastUserFinalAt, t.assistantFirstTokenAt),
    responseMs: delta(t.lastUserFinalAt, t.assistantFinalAt),
  };
}

/** Whether any timing is available yet (controls rendering the compact strip). */
export function hasTimings(v: RealtimeTimingView): boolean {
  return v.offerMs != null || v.readyMs != null || v.firstTokenMs != null || v.responseMs != null;
}
