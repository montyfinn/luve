/**
 * Real email/password auth client for core_api (C4). Client-only — uses the
 * existing endpoints under /api/v1/auth (register / login / me). No Google,
 * realtime, or grading wiring here; the rest of the app stays mock.
 *
 * Base URL comes from config (VITE_CORE_API_URL, default http://localhost:8000).
 * :5173 is already in the core_api CORS allow-list.
 */
import { CORE_API_URL } from "./config";

/** UserRead from core_api (services/core-api/src/schemas/user.py). */
export interface AuthUser {
  id: string;
  username: string;
  email: string;
  fluency_level: number;
  quota_minutes: number;
  is_active: boolean;
  is_banned: boolean;
  created_at: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterInput {
  username: string;
  email: string;
  password: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

/** Friendly, surfaceable error — never carries secrets. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Turn a FastAPI `detail` (string | validation array | object) into a message. */
function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return fallback;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(CORE_API_URL + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Couldn't reach the server. Is the API running?", 0);
  }
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(formatDetail((payload as { detail?: unknown })?.detail, `Request failed (${res.status}).`), res.status);
  }
  return payload as T;
}

/** POST /api/v1/auth/register → UserRead (no token). */
export async function register(input: RegisterInput): Promise<AuthUser> {
  return postJson<AuthUser>("/api/v1/auth/register", input);
}

/** POST /api/v1/auth/login → bearer token. */
export async function login(input: LoginInput): Promise<string> {
  const token = await postJson<TokenResponse>("/api/v1/auth/login", input);
  if (!token?.access_token) throw new ApiError("Sign-in response was missing a token.", 0);
  return token.access_token;
}

/** GET /api/v1/auth/me with a bearer token → current user. */
export async function fetchMe(token: string): Promise<AuthUser> {
  let res: Response;
  try {
    res = await fetch(CORE_API_URL + "/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError("Couldn't reach the server. Is the API running?", 0);
  }
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(formatDetail((payload as { detail?: unknown })?.detail, "Session check failed."), res.status);
  }
  return payload as AuthUser;
}
