/**
 * Real session creation against core_api (C5). Client-only — uses the existing
 * POST /api/v1/sessions with the stored bearer token. No realtime/WebRTC,
 * microphone, or grading here; the gateway base URL is prepared for the later
 * WebRTC phase but NOT contacted in this task.
 */
import { CORE_API_URL } from "./config";
import { ApiError } from "./authApi";
import { loadToken } from "./session";

/** Subset of core_api SessionRead the client needs. */
export interface Session {
  id: string;
  status: string;
  started_at: string;
}

export interface CreateSessionOptions {
  sttOnly: boolean;
  muteTts: boolean;
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return fallback;
}

/** POST /api/v1/sessions → SessionRead. Requires a stored bearer token. */
export async function createSession(opts: CreateSessionOptions): Promise<Session> {
  const token = loadToken();
  if (!token) {
    throw new ApiError("Please sign in again to start a session.", 401);
  }

  let res: Response;
  try {
    res = await fetch(CORE_API_URL + "/api/v1/sessions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        metadata: {
          source: "luve_client",
          transport: "webrtc_ten",
          stt_only: opts.sttOnly,
          mute_tts: opts.muteTts,
        },
      }),
    });
  } catch {
    throw new ApiError("Couldn't reach the server. Is the API running?", 0);
  }

  const payload = await res.json().catch(() => null);
  if (res.status === 401) {
    throw new ApiError("Your session expired — please sign in again.", 401);
  }
  if (!res.ok) {
    throw new ApiError(
      formatDetail((payload as { detail?: unknown })?.detail, `Couldn't start the session (${res.status}).`),
      res.status,
    );
  }

  const session = payload as { id?: string; status?: string; started_at?: string };
  if (!session?.id) {
    throw new ApiError("Session response was missing an id.", 0);
  }
  return { id: session.id, status: session.status ?? "ready", started_at: session.started_at ?? "" };
}
