/**
 * Client-side auth session persistence. Bearer token + minimal user info are
 * kept in localStorage so a signed-in user survives a refresh. The token is
 * never placed in the URL. logout() clears everything.
 */
import type { AuthUser } from "./authApi";

const TOKEN_KEY = "luve.auth.token";
const USER_KEY = "luve.auth.user";

export interface StoredSession {
  token: string;
  user: AuthUser;
}

/** The stored bearer token, if any (for authenticated API calls). */
export function loadToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function decodeBase64UrlJson(value: string): unknown {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padding = (4 - (normalized.length % 4)) % 4;
  return JSON.parse(atob(normalized + "=".repeat(padding)));
}

/** JWT exp claim in milliseconds since epoch, or null if the token is absent/malformed. */
export function getTokenExpiryMs(token: string | null = loadToken()): number | null {
  if (!token) return null;
  const [, payload] = token.split(".");
  if (!payload) return null;

  try {
    const claims = decodeBase64UrlJson(payload) as { exp?: unknown };
    return typeof claims.exp === "number" && Number.isFinite(claims.exp) ? claims.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Milliseconds until JWT expiry. Accepts injected token/now for smoke tests. */
export function getMsUntilExpiry(token: string | null = loadToken(), nowMs = Date.now()): number | null {
  const expiryMs = getTokenExpiryMs(token);
  return expiryMs == null ? null : expiryMs - nowMs;
}

/** True when the stored JWT exists and expires within thresholdMs. */
export function isTokenExpiringSoon(
  thresholdMs: number,
  token: string | null = loadToken(),
  nowMs = Date.now(),
): boolean {
  const remainingMs = getMsUntilExpiry(token, nowMs);
  return remainingMs != null && remainingMs <= thresholdMs;
}

export function loadSession(): StoredSession | null {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const rawUser = localStorage.getItem(USER_KEY);
    if (!token || !rawUser) return null;
    return { token, user: JSON.parse(rawUser) as AuthUser };
  } catch {
    return null;
  }
}

export function saveSession(token: string, user: AuthUser): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* storage unavailable (private mode) — session stays in-memory only */
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}
