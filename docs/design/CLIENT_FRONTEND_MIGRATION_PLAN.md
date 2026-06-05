# LUVE `client/` Frontend Migration Plan

> **Status:** architecture plan only — **no `client/` code exists yet**. This document
> reduces migration risk *before* implementation.
> **Baseline:** `main == origin/main == d3505cb` (clean). The earlier static-shell attempt
> `37ada16` is preserved on branch `backup/ui-shell-37ada16` and is **not** part of this plan.
> **Hard rule:** the existing static control center (`services/core-api/src/static/index.html`,
> served at `/control-center`) is the **fallback and is not modified** by this migration until
> an explicit cutover decision.

---

## 1. Decision summary

Build the Claude Design UI as a real **Vite + React + TypeScript** app under `client/`, using a
**hybrid serving model (Option C)**:

- **Dev:** Vite dev server on `:5173`, talking to the existing `core_api` (`:8000`) and
  `ten_gateway` (`:8080`). No backend code changes needed — `:5173` is **already** in the
  CORS allow-list (`src/core/cors.py`).
- **Prod / demo:** `client/` builds to static `dist/`, copied into the `core_api` image and
  served **same-origin** at the **new `/app` route**. The old `/control-center` stays as an
  untouched fallback; cutover (repointing or retiring `/control-center`) is a **later explicit
  decision**, not part of this migration's default path.

**Settled decisions (this finalization):**
- **Initial new-client route is `/app`.** `/control-center` is **not** replaced initially and
  remains the old static fallback. Cutover is deferred to an explicit later decision (§8 Phase 11).
- **Initial routing is a minimal app state machine / internal state flow** (intro → auth →
  practice), **not** React Router. React Router is introduced **later only if** real routes /
  deep links become necessary (e.g. session history, settings, shareable analysis pages).

The **first implementation commit is a skeleton only** — a Vite app under `client/` with static
screens and **no backend calls, no compose wiring, no serve route**. The static UI is untouched.
This keeps the first review tiny and the rollback free.

**Why this is safe:** the existing realtime/auth/grading backends are unchanged; the client is
purely additive under `client/` plus (later) one additive serve route and one Dockerfile build
stage. Every phase rolls back to the working static UI.

## 2. Verified integration facts (evidence-grounded)

| Concern | Fact | Source |
|---|---|---|
| Current UI serving | `core_api` **and** `ten_gateway` both serve `static/index.html` at `/control-center`; `/static` mounted on both | `src/main.py:31,39-41`, `run_ten.py:85,102-104` |
| **CORS (core_api)** | Configurable via `get_cors_allow_origins()`; **default already includes `http://localhost:5173` + `http://127.0.0.1:5173`** (and :3000/:8000/:8080); overridable by `CORS_ALLOW_ORIGINS` env | `src/core/cors.py` |
| CORS (gateway) | `allow_origins=["*"]` | `run_ten.py:88-90` |
| Google redirect target | Built from `settings.control_center_url` (default `http://localhost:8000/control-center`, env `CONTROL_CENTER_URL`); appends `?google_code=` / `?auth_error=` | `config.py:20-21`, `auth.py:64-65` |
| Auth endpoints | `POST /api/v1/auth/register`, `/login`, `GET /me`, `GET /google/start` (302 or **404** when paused), `GET /google/callback`, `POST /google/exchange {google_code}` | `api/v1/auth.py` |
| Sessions endpoints | `POST /api/v1/sessions`, `GET /{id}`, `GET /{id}/grading/status`, `GET /{id}/grading` — **no list endpoint** | `api/v1/sessions.py:16,29,42,55` |
| Grading contract | `GradingRead`: `overall/fluency/grammar/vocab_score` (0–10), `pronunciation_score?` (nullable), `ai_summary_feedback`, `detailed_corrections[]`, `skill_feedback[]`, `provider`, `grader_version`, `is_dev_preview`, `error_code?` | `schemas/session.py:30-58` |
| Realtime (gateway) | `POST /rtc/offer` (SDP), `/rtc/ice`, `/rtc/cmd` (START/FLUSH/BARGE_IN/END_SESSION), `GET /rtc/health`, `/healthz`, `/readyz`; DataChannels `luve-control` + json; events `stt_result`/`subtitle`, `assistant_stream`/`assistant_final`, `assistant_audio`/`assistant_audio_meta`, `session_ended`, `stt_ready`, `llm_error` | `run_ten.py`, current `index.html` handlers |

**Answers to Phase-1 questions:**
1. **Current UI served** as one static file by FastAPI `FileResponse` on both :8000 and :8080.
2. **Backend APIs the client must call:** auth (register/login/me/google), sessions
   (create/get/grading/grading-status) on `core_api` :8000.
3. **Gateway/WebRTC the client must call:** `/rtc/offer|ice|cmd`, `/rtc/health` on
   `ten_gateway` :8080, plus the DataChannel event stream.
4. **Google redirect today:** backend redirects the browser to `CONTROL_CENTER_URL` with a
   one-time `?google_code=` (or `?auth_error=`); the page exchanges it via `POST /google/exchange`
   and scrubs the URL. (Live login paused → `/google/start` returns 404 today.)
5. **If client runs on :5173:** REST/gateway calls work — `:5173` is already CORS-allowed and
   the gateway allows `*`. **Only** change needed for Google is pointing `CONTROL_CENTER_URL`
   at the client's callback route (env-only). No backend code change.
6. **If client build served by core_api:** same-origin → simplest; `CONTROL_CENTER_URL` points
   at the in-app callback route (e.g. `/app`). Needs a Node build stage + one additive serve
   route; existing endpoints untouched.

## 3. Options considered

| Option | Dev UX | OAuth/CORS | Backend change | Prod story | Verdict |
|---|---|---|---|---|---|
| **A** — built `dist/` served by core_api only | weak (rebuild to see changes) | easy (same-origin) | Node build stage + serve route | clean | half of the answer |
| **B** — Vite dev `:5173` only | best | already CORS-allowed; `CONTROL_CENTER_URL` change for OAuth | none (CORS already covers :5173) | **missing** (no prod artifact) | half of the answer |
| **C** — hybrid (dev `:5173` + built `dist/` served by core_api) | best | both covered | additive build stage + serve route | clean, same-origin demo | **RECOMMENDED** |

## 4. Recommended architecture (opinionated)

**Option C (hybrid).** Rationale against the criteria:
- **Google OAuth correctness:** prod/demo served same-origin at :8000 → simplest, unchanged
  default. Dev :5173 only needs `CONTROL_CENTER_URL` repointed (env-only). CORS already allows
  :5173 — no code risk.
- **Minimize backend changes:** zero now (skeleton phase); later just **one additive serve
  route** + a Dockerfile build stage. Existing endpoints, auth, realtime, grading untouched.
- **Professional UI:** a real Vite/React/TS app cleanly realizes the Claude Design direction
  (tokens, IA, motion) at ~80–90% fidelity.
- **Don't block current backend:** the static `/control-center` remains the live, working UI
  the whole time.
- **Clear dev workflow:** `cd client && npm install && npm run dev`.
- **Easy rollback:** the static UI is never touched; the client is additive.
- **Demo-compatible:** the built `dist/` at `/app` gives a same-origin, OAuth-friendly demo.

### Stack
- **Vite + React 18 + TypeScript.** React is already the design package's own framework (the
  prototype is React 18 + Babel-standalone), so React is the lowest-friction translation target.
- **CSS: plain CSS + CSS custom properties**, adopting `docs/design/luvedesign/assets/luve-tokens.css`
  (already vanilla CSS variables: palette / status / spacing / radius / shadow / motion). Use
  **CSS Modules** for component scoping. **Do NOT add Tailwind** — the design package uses tokens +
  semantic classes, not utilities; adding Tailwind is unjustified churn and a second styling system.
- **API client layer:** a thin typed `fetch` wrapper in `client/src/api/` with two base URLs
  from Vite env (`VITE_CORE_API_URL` default `http://localhost:8000`, `VITE_GATEWAY_URL` default
  `http://localhost:8080`). Bearer token kept in memory + optional `localStorage` (mirrors the
  current "remember" behavior). **No JWT in URL.**
- **Routing/state — minimal app state machine (decided).** Use a lightweight internal
  view-state machine mirroring today's `landing → auth → practice` flow (a single `view` state
  + transitions), **not** React Router. The app has no real routes or deep links yet, so a
  router is unnecessary weight. **React Router is deferred** and added later only if real routes /
  deep links become necessary (session history, settings, shareable analysis pages). The Google
  callback is handled in-app by reading `google_code`/`auth_error` from the URL and scrubbing it
  (no route needed). Realtime/session state lives in a dedicated `useRealtimeSession` hook (typed
  port of the proven vanilla logic). No global state library needed at this scale.
- **Not in the first skeleton:** Session History (no `GET /sessions`), cat effects/Lottie
  (later motion phase), any backend mutation.

### Why NOT directly copy the Claude Design prototype
The package's `proto-*.jsx` + `LUVE Practice - Prototype.html` are a **Babel-in-browser** React
prototype using **CDN** React/Babel/Lottie, **mock data**, and ~2.3 MB cat Lottie assets. Copying
it would (a) pull CDN runtime deps and mock behaviors into production, (b) not match the real
backend contract, and (c) drag in the heavy cat assets prematurely. Instead we **rebuild** as a
proper typed Vite app, **adopting** the tokens (`luve-tokens.css`) and the visual structure /
screen specs from `LUVE Control Center - Design Spec.html`, wired to the **real** APIs. The
prototype/spec are **reference**, per `CLAUDE_DESIGN_INTAKE_REVIEW.md`.

## 5. API / auth / realtime / grading mapping (client modules)

- `api/auth.ts` → register/login/me; Google exchange + URL-scrub; bearer storage.
- `api/sessions.ts` → create session; `getGradingStatus`; `getGrading` (typed `GradingRead`,
  0–10 scores, nullable pronunciation, `is_dev_preview` → preview banner).
- `realtime/useRealtimeSession.ts` → faithful TS port of the working `index.html` WebRTC logic
  (offer/ICE/cmd, `luve-control` + json DataChannels, event dispatch: STT partial/final,
  assistant stream/final, audio meta → TTS state, `session_ended`, `stt_ready`, `llm_error`).
  **Reference = the proven static `index.html` JS, not the prototype.**
- `api/health.ts` → `/readyz` (core_api), `/rtc/health` (gateway) for the diagnostics drawer.

## 6. Google OAuth implications

- **Dev (client :5173):** set `CONTROL_CENTER_URL=http://localhost:5173/auth/callback` (client
  handles `google_code`). CORS already allows :5173. **Env-only**, no `auth.py` change.
- **Prod/demo (served at :8000/app):** set `CONTROL_CENTER_URL=http://localhost:8000/app`
  (same-origin). Simplest.
- **Either way:** the client must replicate the existing safe flow — detect `google_code` /
  `auth_error` in the URL → `POST /api/v1/auth/google/exchange` → store token → **scrub the URL**;
  map `auth_error` codes to friendly copy; treat `/google/start` **404** as the calm
  "Google login is not configured yet" state. **Google live login stays paused** until creds exist;
  this plan does not enable it.

## 7. Docker / compose implications

- **Now (skeleton):** none. `client/` is a standalone npm project; not referenced by compose.
- **Dev:** run outside compose (`npm run dev`) initially — simplest, and :5173 is pre-allowed.
  Optionally add a compose `client` service under a `dev` profile later (kept out of the default
  `app` profile so the stack is unaffected).
- **Prod/demo:** add a **multi-stage** build — a Node stage builds `client/dist`, copied into the
  `core_api` image; core_api serves it at `/app` via `StaticFiles`/`FileResponse`. This is one
  additive route + one build stage; **existing `/control-center`, `/static`, and all API routes
  are unchanged.** No new long-running runtime service in production.

## 8. Phased implementation plan

Each phase is a small, independently-revertable commit. The static UI is untouched until Phase 11.

| # | Phase | Files touched | Risk | Verify | Rollback |
|---|---|---|---|---|---|
| 1 | **Client skeleton + static screens** (Vite/React/TS, tokens adopted, screens from Design Spec, **no backend calls, no cat, no history**) | new `client/**` only | low | `npm run build`, `tsc --noEmit`, local `npm run dev` visual | delete `client/` commit; static UI unaffected |
| 2 | **Auth API integration** (register/login/me, bearer storage) | `client/src/api/auth.ts`, auth screens | med | login against running core_api; 401 handling | revert phase commit |
| 3 | **Google disabled/enabled states** (exchange + scrub + 404 calm state) | `client/src/api/auth.ts`, callback route | med (OAuth) | 404 → calm message; dummy exchange → safe error | revert; `CONTROL_CENTER_URL` unchanged in repo |
| 4 | **Session create / gateway URL handling** (create session, base-URL config) | `client/src/api/sessions.ts`, config | med | `POST /sessions` 201; URL fields in drawer | revert |
| 5 | **Realtime / WebRTC** (typed port of proven JS) | `client/src/realtime/**` | **high** | offer 200, ICE flow, DataChannels open, mic mute/barge | revert; static UI still works |
| 6 | **Transcript / live states** (final+partial, assistant stream, TTS state) | realtime hook + live view | med | live subtitles + assistant text render | revert |
| 7 | **Analysis / grading** (status poll + `GradingRead` render, dev-preview banner) | `client/src/api/sessions.ts`, analysis view | med | pending→graded; preview vs real; insufficient-evidence | revert |
| 8 | **Diagnostics drawer** (URLs, token, health, event log — collapsed) | diagnostics components | low | drawer holds operator controls; health dots | revert |
| 9 | **Cat effects + motion/perf** (per intake §4a: audit asset size, lazy-load, reduced-motion + static fallback, budget) | motion/cat module | med (perf) | bundle/asset budget; `prefers-reduced-motion`; no jank | revert; cat is isolated |
| 10 | **Docker / core_api serving** (Node build stage → `dist` → serve at `/app`) | `services/core-api/Dockerfile`, `src/main.py` (one additive route), compose (optional dev svc) | med | `/app` serves built client; `/control-center` still serves old UI | revert route + build stage |
| 11 | **Cutover decision** (keep both, or repoint `/control-center` / retire static) | docs + optional route change | low→med | explicit review; both routes verified | keep static as fallback |

## 9. Rollback plan

- **Per phase:** revert the phase commit; nothing else depends on it.
- **Whole migration:** the static `/control-center` is never modified through Phase 10, so the
  live product keeps working regardless of client state. Removing the `/app` route + build stage
  fully reverts to today's behavior.
- **Reuse prior work:** `backup/ui-shell-37ada16` holds the earlier static-shell experiment if any
  copy/structure is worth cherry-picking.
- **No data risk:** UI-only; no DB/RabbitMQ/Redis/schema changes anywhere in this plan.

## 10. Decisions & open items

### Resolved in this finalization
- **Client serve route = `/app`.** `/control-center` is **not** replaced initially and stays the
  old static fallback. Cutover is a later explicit decision (see open item: cutover timing).
- **Routing = minimal app state machine / internal state flow** (intro → auth → practice).
  **React Router deferred** until real routes / deep links are needed (session history, settings,
  shareable analysis).

### Still open (resolve with/before implementation)
1. **Dev integration:** run-outside-compose (recommended first) vs a compose `client` service under
   a `dev` profile.
2. **Toolchain:** ESLint + Prettier config, TypeScript strictness level, Node version pin for the
   build stage.
3. **"Recent session" affordance:** reuse `last-session-id` only (no list) until a `GET /sessions`
   endpoint is greenlit (Session History stays deferred).
4. **Fonts:** self-host the design fonts (Newsreader / Hanken Grotesk / JetBrains Mono, OFL) vs
   system-font fallback — avoid CDN render-block.
5. **Cutover timing:** demo on `/app` first, retire/repoint `/control-center` later — or run both
   side by side indefinitely.

---

*Planning artifact only. No `client/` code created; no runtime, backend, compose, `.env`, or
design-package changes. Implementation must follow the Design → Code → Review workflow, starting
with the Phase-1 skeleton.*
