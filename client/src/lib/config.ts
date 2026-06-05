/**
 * Client runtime config — base URLs for the two origins the browser talks to.
 * core_api (REST/auth/sessions) and ten_gateway (realtime, later phase).
 * Overridable via Vite env; defaults match local dev. :5173 is already in the
 * core_api CORS allow-list.
 */
export const CORE_API_URL = (import.meta.env.VITE_CORE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export const GATEWAY_URL = (import.meta.env.VITE_GATEWAY_URL ?? "http://localhost:8080").replace(/\/+$/, "");
