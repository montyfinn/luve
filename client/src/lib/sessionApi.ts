/**
 * Real session calls against core_api. Client-only — uses /api/v1/sessions with
 * the stored bearer token. No realtime/WebRTC, microphone, transcript replay,
 * or grading here; the gateway base URL is prepared for the later WebRTC phase
 * but NOT contacted in this task.
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

export interface SessionHistoryItem {
  id: string;
  lesson_id: string | null;
  status: string;
  total_tokens: number;
  manual_stops_count: number;
  started_at: string;
  ended_at: string | null;
}

export interface SessionHistoryResponse {
  items: SessionHistoryItem[];
  limit: number;
  offset: number;
  total: number;
}

export interface ListSessionsOptions {
  limit?: number;
  offset?: number;
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return fallback;
}

function asHistoryItem(value: unknown): SessionHistoryItem | null {
  const item = value as Partial<SessionHistoryItem> | null;
  if (!item || typeof item !== "object") return null;
  if (
    typeof item.id !== "string" ||
    typeof item.status !== "string" ||
    typeof item.total_tokens !== "number" ||
    typeof item.manual_stops_count !== "number" ||
    typeof item.started_at !== "string"
  ) {
    return null;
  }

  return {
    id: item.id,
    lesson_id: typeof item.lesson_id === "string" ? item.lesson_id : null,
    status: item.status,
    total_tokens: item.total_tokens,
    manual_stops_count: item.manual_stops_count,
    started_at: item.started_at,
    ended_at: typeof item.ended_at === "string" ? item.ended_at : null,
  };
}

function parseHistoryResponse(payload: unknown): SessionHistoryResponse {
  const body = payload as Partial<SessionHistoryResponse> | null;
  if (!body || typeof body !== "object" || !Array.isArray(body.items)) {
    throw new ApiError("Session history response was malformed.", 0);
  }

  const items = body.items.map(asHistoryItem);
  if (items.some((item) => item === null)) {
    throw new ApiError("Session history response included an invalid item.", 0);
  }

  return {
    items: items as SessionHistoryItem[],
    limit: typeof body.limit === "number" ? body.limit : items.length,
    offset: typeof body.offset === "number" ? body.offset : 0,
    total: typeof body.total === "number" ? body.total : items.length,
  };
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

/** GET /api/v1/sessions → lightweight authenticated history page. */
export async function listSessions(opts: ListSessionsOptions = {}): Promise<SessionHistoryResponse> {
  const token = loadToken();
  if (!token) {
    throw new ApiError("Please sign in again to view recent sessions.", 401);
  }

  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  const query = params.toString();

  let res: Response;
  try {
    res = await fetch(CORE_API_URL + "/api/v1/sessions" + (query ? `?${query}` : ""), {
      headers: {
        Authorization: `Bearer ${token}`,
      },
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
      formatDetail((payload as { detail?: unknown })?.detail, `Couldn't load recent sessions (${res.status}).`),
      res.status,
    );
  }

  return parseHistoryResponse(payload);
}
