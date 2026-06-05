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
