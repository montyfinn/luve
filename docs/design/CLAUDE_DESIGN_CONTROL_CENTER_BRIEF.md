# LUVE Control Center — Design Brief for Claude Design

> **Audience:** a product/UX designer (Claude Design) who has *not* read the codebase.
> **Goal:** produce a professional UI/UX specification for the LUVE control center that
> is faithful to the real backend, not aspirational marketing.
> **Status of this brief:** source-grounded audit at public HEAD `6fa9665`
> (`main == origin/main`). Evidence file paths are cited inline and in the appendix.

---

## 1. Title & purpose

LUVE is an **AI-assisted English speaking-practice system**. A learner signs in, starts a
realtime voice session (microphone → speech-to-text → LLM tutor reply → text-to-speech),
and after the session ends the conversation is **graded asynchronously** and shown as a
Session Analysis panel.

Today the product is delivered through a **single static HTML control center**
(`services/core-api/src/static/index.html`) that currently reads like an *engineering
debug console*. The business goal is to evolve it into a **polished, learner-first product**
that still preserves the operator/developer visibility the team relies on — without
inventing backend capabilities that do not exist.

This brief tells Claude Design exactly what the backend supports, what the UI must expose,
which flows and states are required, and which constraints are non-negotiable.

### 1.1 First-30-seconds demo priority (design for this path first)

The single most important thing this UI must do well is carry a new visitor through one
successful practice loop without friction. Design this **happy path** before anything else:

> **landing → sign in (email or Google) → Start practice → speak / listen → end → analysis**

- **Start practice is the primary call to action.** On the authenticated home it is the one
  obviously-primary button; nothing competes with it visually.
- **Diagnostics are hidden by default.** URLs, tokens, event logs, provider/health readouts
  do not appear in this path; they live in a collapsed Developer diagnostics drawer (§13)
  that a learner never needs to open to complete the loop.
- **Every step has a calm, learner-legible state** — no engineering jargon on the happy path.
  Sign-in confirms who you are; the live view shows speaking/listening/thinking plainly;
  ending leads to an analysis that loads gracefully (§12).

Everything else in this brief (operator visibility, full state matrix, edge cases) supports
this loop; it does not outrank it.

## 2. How Claude Design should use this brief

- **Produce a UX/UI specification, not code.** Layouts, component hierarchy, copy,
  interaction flows, responsive behavior, and state coverage — yes. Implementation diffs — no.
- **Do not invent backend capabilities.** If a capability is not in §3/§4/§9, treat it as
  out of scope or mark it explicitly as a *proposed future idea* in a clearly separated section.
- **Separate certainty levels.** When you reference a capability, respect the
  *Implemented / Gated / Default-off / Future* classification in §4.
- **Design for two audiences in one product** (§6): a **learner** (primary) and a
  **developer/operator** (secondary, must stay accessible but not dominate).
- A later **Claude Code** phase will implement your spec *surgically* against the existing
  single HTML file — see §19 for the constraints that keeps it implementable.

## 3. Non-negotiable truths from the current backend

These are verified against source. The design must not contradict them.

1. **Two app services, two ports.** `core_api` on **:8000** (REST, auth, session records,
   serves the control center, readiness) and `ten_gateway` on **:8080** (WebRTC realtime
   voice pipeline). The same static HTML is served by *both* (`/control-center` on each).
   *Evidence: `services/core-api/src/main.py`, `services/core-api/run_ten.py`, `README.md`.*
2. **The browser talks to two origins.** REST/auth/session/grading calls go to `core_api`
   (:8000); the realtime SDP offer/ICE/commands go to `ten_gateway` (:8080). The UI already
   exposes both base URLs as editable fields. *Evidence: `run_ten.py` (`/rtc/offer`,
   `/rtc/ice`, `/rtc/cmd`), `static/index.html` (`core-api-url`, `gateway-url`).*
3. **One realtime session per node, by design.** The gateway is hard-capped at a single
   active WebRTC session; a second is rejected with HTTP 503. The UI must communicate
   "single session" rather than implying multi-session concurrency.
   *Evidence: `docs/ai/CLAUDE_CODE_HANDOFF.md` §L3.*
4. **Grading is asynchronous.** When a session ends, a job is queued (RabbitMQ) and a worker
   writes results later. The UI must treat analysis as *eventually available*, with
   pending/processing states — never assume it is ready at session end.
   *Evidence: `services/grading-worker/src/worker.py`, `README.md`, HANDOFF §E.*
5. **Grading may be real or a placeholder.** Depending on environment, grading runs a real
   LLM (Groq) **or** an offline deterministic "fake" grader. The UI must visibly distinguish
   a real result from a dev-preview/placeholder result (the API exposes this).
   *Evidence: `services/grading-worker/src/worker.py`, `schemas/session.py` (`is_dev_preview`,
   `provider`, `grader_version`).*
6. **Not production-ready.** No TLS/SSO/observability stack; STT validated only in a
   constrained demo config (forced English, `small.en`). The UI must not display fake
   "production-ready" / "secure" badges. *Evidence: `README.md` Status section.*
7. **Security constraints (hard):** the frontend never handles the Google client secret;
   the Luve JWT must **never** appear in a URL; Google sign-in completes via a backend
   **one-time `google_code`** exchange. *Evidence: `services/core-api/src/api/v1/auth.py`,
   `services/core-api/src/services/google_oauth.py`.*

## 4. Implemented / gated / future capability matrix

| Capability | Status | Notes / evidence |
|---|---|---|
| Email + password **register/login**, JWT bearer, `/me` | **Implemented & verified** | Login returns a bearer token; verified live this cycle. `api/v1/auth.py` |
| **Session create** (`POST /sessions`, status `ready`) | **Implemented** | `api/v1/sessions.py`, `schemas/session.py` |
| **Realtime voice** (WebRTC offer/ICE/cmd, STT→LLM→TTS) | **Implemented; dev-verified** | Stress-tested in dev (noise/short_english/TTS drain). `run_ten.py`, HANDOFF §D/§H |
| **Session transcript persistence** (`raw_backup_json`) | **Implemented** | Saved on session end. HANDOFF §E |
| **Async grading** (fake grader default) | **Implemented & verified** | `fake_grader.v1`. worker.py |
| **Real LLM grading (Groq)** | **Implemented; env-gated** | Runs only when `GRADING_PROVIDER=llm` + key. Verified in prior cycles. worker.py |
| **Session Analysis API** (`/grading`, `/grading/status`) | **Implemented** | Status set: graded/processing/pending/insufficient_evidence/failed. `schemas/session.py` |
| **Google OAuth (backend + button)** | **Implemented but PAUSED/gated** | Disabled until root `.env` has Google creds → endpoints return **404**; button shows "Google login is not configured yet." Disabled-state verified; **live login not yet end-to-end verified.** `auth.py`, HANDOFF §L6 |
| **Transactional outbox relay** (delivery recovery) | **Default-OFF** | Inline publish is the live path; relay is operator-enabled only. Not user-facing. HANDOFF §L5 |
| **GPU STT** | **Opt-in** | CPU is the default; GPU via a compose override. Not a UI concern except latency. HANDOFF §L4 |
| **Lessons / curriculum** | **Schema only, no API/UI** | `lessons` table + `sessions.lesson_id` exist but there is no lessons endpoint or UI. Treat as **future/out-of-scope** for now. `infrastructure/db-init/01-init.sql` |
| **Pronunciation score** | **Optional / may be absent** | Nullable; unavailable when audio evidence is insufficient. `schemas/session.py`, README |
| Multi-session, teacher/admin roles, payments, mobile app | **Future / not present** | Do not design as if these exist. |

## 5. Current frontend inventory (what exists today)

**File:** `services/core-api/src/static/index.html` — one large file: markup + Tailwind-style
utility classes + scoped `cc-*` classes (`styles.css`) + a single inline `<script>`.

**Three top-level views** (toggled by `body` class `view-landing` / `view-auth` / `view-app`,
containers `#cc-view-landing`, `#cc-view-auth`, `#cc-view-app`):

1. **Landing** — product blurb ("Industrial AI Lab Console" tone) + three feature cards
   (Microphone Pipeline, Speaking loop, Telemetry Analytics) + CTAs `#goto-login-btn`,
   `#goto-register-btn`.
2. **Auth** — card with login/register tabs (`#auth-tab-login`, `#auth-tab-register`),
   inputs `#auth-email`, `#auth-password`, `#auth-username`, actions `#login-btn`,
   `#register-btn`, `#google-login-btn`, `#remember-token`, `#back-to-welcome-btn`,
   status line `#auth-state`.
3. **App / control console** — collapsible sections: `#cc-sec-checklist` (readiness steps),
   `#cc-sec-session` (session + URLs), `#cc-sec-controls` (realtime controls),
   `#cc-sec-diagnostics` (logs/endpoints), `#cc-sec-insights` (grading).

The concrete implementation inventory — the existing element IDs Claude Code must preserve,
and the current status-theme vocabulary in code — is **not** design-facing material and has
been moved to **Appendix A (§22)** so it sits with the Claude Code constraints rather than
alongside learner UX. Designers can ignore it; it exists so the later implementation phase
maps cleanly onto the current file.

**Current strengths to preserve:** working auth (incl. Google button), explicit
API/gateway/token controls useful for dev, live transcript display, visible operational
status, and a Session Analysis card already wired to the grading API.

**Current UX debt the design must fix:**
- Reads like a raw backend console; learner-facing and developer-facing controls are mixed.
- Weak hierarchy — many controls visible at once; the primary action ("start practicing")
  is not obviously primary.
- Setup plumbing (API URL, gateway URL, bearer-token override, endpoints) is presented at
  the same level as the practice experience.
- Session Analysis presentation is functional but not professional/learner-grade.
- Onboarding is thin; the landing view explains engineering, not learner value.
- Marketing/wording overstates ("industrial", "telemetry") relative to a demo product.

## 6. Required audience modes

The product serves two audiences through **one** interface. The design must make the learner
path primary and the operator path present-but-secondary.

- **Learner mode (primary):** sign in → start a practice session → see speaking/listening
  state → receive the AI tutor's spoken reply → end session → view analysis & corrections.
  Minimal jargon. No need to understand ports, tokens, or providers.
- **Developer / operator mode (secondary):** core-api/gateway URL controls, bearer-token
  override, connection diagnostics, health/provider/environment status, event log. Must be
  reachable (this is a dev tool today) but **tucked into a drawer/secondary surface**, never
  competing with the learner flow.

## 7. Required user journeys

1. **First visit / unauthenticated:** clear product explanation (learner value, not
   engineering), then sign in / register / **Continue with Google**. When Google is disabled,
   show the safe "not configured yet" message (it must not look broken).
2. **Authenticated home:** show who is signed in and a single prominent **Start practice**
   call to action; optional session setup (see §11) lives here, collapsed by default.
3. **Live session:** connection state, mic/voice state, streaming transcript, AI reply +
   audio state, a clear **End session** action, and graceful error/reconnect states.
4. **Post-session:** analysis loading/queued/unavailable states; then the grading result —
   scores, corrections/coaching, and a clear **real vs dev-preview** indicator; raw
   operational metadata tucked away.
5. **Settings / diagnostics:** API & gateway URLs, token controls, health status,
   provider/environment status, dev-only warnings — all secondary.

## 8. Required UI states (design must cover every one)

**Auth:** logged out · logging in (busy) · login failed (inline error) · Google **disabled**
("not configured yet") · Google **redirect in progress** · Google **`auth_error`** returned
(map codes: `state_mismatch`, `account_exists`, `link_conflict`, `email_unverified`,
`exchange_failed`, `cancelled` → friendly copy) · signed in · token expired / unauthorized
(401/403 → prompt re-auth).

**Realtime session:** idle (signed in, no session) · creating session · connecting (RTC
negotiation) · connected/listening · user speaking · processing STT (partial → final) · AI
thinking · TTS playing (AI speaking) · interrupted / barge-in · reconnecting · ending ·
ended.

**Grading / analysis:** pending · processing · **insufficient evidence** (too little speech
to grade — actionable message, not an error) · graded (real LLM) · graded (fake/dev-preview,
clearly labeled) · failed (with safe error code) · no transcript/evidence.

**System health:** core_api unhealthy (DB down) · gateway unhealthy / unreachable · grading
stalled — *inferred* from results staying pending/processing; there is no direct
worker-health API · degraded (e.g., CPU STT high latency).

**Responsive:** mobile / narrow viewport for at least the learner journey (auth → session →
analysis); the operator drawer may be desktop-first.

> Note: today's code emits only a *subset* of these (e.g., `disconnected`/`thinking`/`ready`/
> `error`/`llm-error`). The design should **define a visual/copy treatment for every state**
> above so the system is complete on paper. But at implementation time a state is **only shown
> when it maps to a concrete backend event or probe** — Claude Code wires the states backed by
> real events/signals and leaves the rest as defined-but-dormant treatments, **not** as fake
> UI that asserts a condition the backend can't actually report. No invented telemetry, no
> placeholder readouts dressed as live data.

## 9. Data / API contract summary (for the designer)

REST is on `core_api` (:8000); realtime is on `ten_gateway` (:8080). Auth is a **bearer JWT**
(`Authorization: Bearer <token>`) returned by login/exchange and stored client-side.

**Auth (`/api/v1/auth`)** — `POST /register` → user profile · `POST /login` → `{access_token,
token_type}` · `GET /me` → profile · `GET /google/start` (302→Google, or **404** when
disabled) · `GET /google/callback` (backend only) · `POST /google/exchange` `{google_code}`
→ `{access_token}`. *Evidence: `api/v1/auth.py`.*

**Sessions (`/api/v1/sessions`)** — `POST ""` → session (`status:"ready"`) · `GET /{id}` →
session · `GET /{id}/grading/status` → `{status, student_word_count?, reason?, error_code?}`
where status ∈ `graded|processing|pending|insufficient_evidence|failed` · `GET /{id}/grading`
→ full result. *Evidence: `api/v1/sessions.py`, `schemas/session.py`.*

**Grading result (`GradingRead`)** fields the analysis UI can rely on: `overall_score`,
`fluency_score`, `grammar_score`, `vocab_score`, `pronunciation_score?` (nullable),
`ai_summary_feedback` (text), `detailed_corrections[]`, `skill_feedback[]`, `input_quality{}`,
`provider`, `grader_version`, `is_dev_preview`, `error_code?/error_message?`. Scores are on a
**0–10 scale**. *Evidence: `schemas/session.py`, `infrastructure/db-init/01-init.sql`.*

**Realtime (`ten_gateway`)** — `POST /rtc/offer` (SDP), `POST /rtc/ice`, `POST /rtc/cmd`
(e.g. FLUSH / BARGE_IN / END_SESSION), `GET /rtc/health` (session snapshot). Events the client
observes: STT partial/final, `assistant_stream` (LLM text), `assistant_audio_meta` (TTS
chunks), session end. *Evidence: `run_ten.py`, `static/index.html` event handlers.*

**Health** — `core_api GET /readyz` = DB reachable (200/503); `ten_gateway GET /readyz` =
shallow startup readiness only; `GET /healthz` (gateway) = liveness. *Evidence: `main.py`,
`run_ten.py`, HANDOFF §L2.*

## 10. Auth & Google OAuth requirements

- Support **email + password** (register has username ≥3, password ≥8) and **Continue with
  Google** side by side.
- **Google flow (server-driven):** the button navigates to `/api/v1/auth/google/start`; the backend
  redirects to Google; after consent the user returns to the control center with a one-time
  `google_code` in the URL; the frontend immediately exchanges it for a JWT and **scrubs the
  URL**. The design must present: a normal button, a *redirecting* state, a *signed in with
  Google* success, and friendly mappings for each `auth_error` code (§8).
- **Disabled state is first-class:** when Google env is absent, the button must show a calm
  "Google login is not configured yet." — *not* an error, *not* a raw 404 page.
- **No-auto-link policy (must be reflected in copy):** if a Google email matches an existing
  password account, the user is told to sign in with their password (we never silently link).
- Token lives client-side (today: a token field + optional "remember" in local storage). The
  design may modernize the presentation but **must not** put the token in the URL and **must**
  keep a developer "paste bearer token" escape hatch in the diagnostics drawer.
- **Localhost consistency** for the first Google smoke (`http://localhost:8000/control-center`)
  — relevant to docs/QA, not to visual design, but copy in setup help should mention it.

## 11. Realtime session requirements

- **Single active session** per node — the design must not imply parallel sessions; handle the
  "busy / capacity reached" (503) case gracefully.
- A **session lifecycle** the UI must represent end-to-end: create → connect (WebRTC) →
  listening ↔ speaking ↔ STT processing ↔ AI thinking ↔ AI speaking (TTS) → end.
- **Microphone control** (mute/unmute; mute sends FLUSH to finalize the current utterance),
  **barge-in** (interrupt the AI), and a clear **End session**.
- A **live transcript** with two tiers: a stable *final* transcription and a lighter *partial
  hypothesis*; plus the AI's streaming reply text and an audio playback element.
- **Session options** (optional, collapsed): STT-only mode, mute TTS — these exist today
  (`stt-only`, `mute-tts`) and are useful for testing; in learner mode they can be hidden or
  framed as "practice settings."
- **Graceful degradation:** reconnect attempts, ICE/connection failures, and a CPU-STT
  "higher latency" hint should be representable.

## 12. Grading / session analysis requirements

- Treat analysis as **asynchronous**: design explicit *pending → processing → ready* states
  with a non-annoying refresh/poll affordance (no infinite spinner; offer a manual "Load
  analysis" too — it exists today as `load-grading-btn`).
- **Insufficient-evidence** is a distinct, friendly state ("Not enough speech to grade — try a
  longer session"), *not* a failure.
- The **real-vs-preview distinction is mandatory.** When `is_dev_preview` is true (or
  `grader_version` is the fake grader), show an honest "preview / automatically generated, not
  final pedagogical grading" note. Do not dress a placeholder as a real score.
- **Score presentation:** four primary dimensions — **Fluency, Grammar, Vocabulary, Overall**
  (0–10), plus **Pronunciation** *when present* (nullable; show "not available" gracefully).
  Then an **AI summary** paragraph and a **corrections / coaching** list (`detailed_corrections`,
  `skill_feedback`).
- **Operational metadata** (`provider`, `grader_version`, `input_quality`, timestamps) belongs
  in a secondary/expandable area, not the learner's headline.

## 13. Developer / operator diagnostics requirements

**Hide-by-default rule.** The following are operator concerns and must be **collapsed inside a
single "Developer diagnostics" drawer/panel**, closed by default and absent from the learner
happy path (§1.1): raw bearer-token input, core-api/gateway URL controls, the event log,
provider/grader metadata, and health/readiness diagnostics. A learner can complete a full
practice loop without ever opening this drawer. The one honesty signal that may surface
outside the drawer is the **fake/dev-preview warning** on an analysis result — and even then
it is a calm, secondary note (§12), visible when relevant but never dominant.

Keep, but demote to a **diagnostics drawer / secondary surface**:
- Editable **core-api URL** and **gateway URL** (the app genuinely needs these in dev).
- **Bearer-token override** (paste/clear) as an escape hatch.
- **Health indicators**: core_api `/readyz` (DB), gateway `/readyz`/`/healthz`, and a hint
  when grading is not progressing — *inferred* from repeated pending/processing states; do
  not design a live worker-health probe unless a backend endpoint is added later.
- **Provider / environment status**: which grader is active (fake vs LLM), Google enabled/disabled.
- **Event log** and **STT diagnostics** (final-STT summary, copy button), realtime endpoints.
- Clear **dev-only warnings** (e.g., "demo build — not production-ready"), shown honestly but
  unobtrusively.

## 14. Information architecture recommendation

A learner-first shell with a clearly separated operator drawer. For each section: *purpose ·
required data · primary actions · empty/loading/error · what NOT to feature*.

1. **Top bar / identity & health** — purpose: orientation + trust. Data: signed-in user,
   connection state, condensed health dot. Actions: sign out, open diagnostics. Empty: signed
   out → minimal. Don't feature: raw URLs/tokens.
2. **Auth panel** — purpose: get in. Data: email/password/username, Google button + disabled
   note. Actions: sign in / register / Continue with Google. States: §8 auth. Don't feature:
   developer token field (move to drawer).
3. **Practice home (authenticated)** — purpose: start practicing. Data: user, optional
   practice settings. Action: **Start practice** (primary CTA). Empty: no session yet. Don't
   feature: endpoints/plumbing.
4. **Live conversation workspace** — purpose: the session itself. Data: connection/mic/AI
   states, transcript (final + partial), AI reply + audio. Actions: mute, barge-in, end.
   States: §8 realtime. Don't feature: event log inline.
5. **Transcript timeline** — purpose: see what was said. Data: finalized turns; current partial.
   Empty: "start speaking…". Error: STT degraded hint.
6. **Session controls** — purpose: lifecycle. Actions: create/connect/disconnect/end. Keep
   minimal and obvious.
7. **Session Analysis panel** — purpose: feedback. Data: scores, summary, corrections,
   real/preview flag. States: §8 grading. Don't feature: provider/version in the headline.
8. **Coaching / next steps** — purpose: turn grading into guidance (uses `detailed_corrections`
   / `skill_feedback`). Future-friendly but should use only data that exists.
9. **Developer diagnostics drawer** — purpose: operator visibility. Data/actions per §13.
   Collapsed by default; clearly "for developers."
10. **Settings drawer** — URLs, token, remember-session, theme (if any), dev warnings.

## 15. Visual direction

Target a **professional AI language-lab** feel — calm, trustworthy, high-contrast where it
matters, clear hierarchy, learner-first, with production-grade *status indicators* but no
fake "production-ready" badges. Reduce clutter; make the primary action obvious; keep
diagnostics tidy and secondary. Avoid heavy neon/cyberpunk unless the user later chooses it.

Style anchors (adjectives, not brands): **"professional language lab," "AI coaching cockpit,"
"calm technical product," "learner-first dashboard," "operator-grade reliability, learner-grade
simplicity."** Status color semantics already in code are a reasonable base: green=ready,
amber=busy/thinking, red=error, rose=disconnected — keep them consistent and accessible.

### 15.1 Polish & microinteractions (bounded)

Motion and microinteractions should make the product feel calm and responsive — never flashy.
Keep them subtle, purposeful, and tied to real state changes:

- **View transitions:** gentle cross-fades / slides between auth → home → live → analysis;
  short durations, easing, no bounce or parallax.
- **Live conversational cues:** a quiet, breathing **speaking / listening** indicator on the
  mic; a distinct **AI thinking** affordance while the LLM responds and a **STT processing**
  cue while a partial finalizes — calm pulses, not spinners that imply error.
- **Analysis loading:** use **skeleton placeholders** for the score cards and summary while
  grading is pending/processing, rather than a single dead spinner.
- **Reduced motion:** honor `prefers-reduced-motion` — replace animated cues with static
  state labels/icons; never gate comprehension on motion.
- **Do not:** neon/cyberpunk glow, gratuitous gradients, decorative "AI sparkle" noise,
  looping background animation, or any motion that competes with the Start-practice CTA.

## 16. Accessibility & responsive requirements

- WCAG-minded contrast; do not rely on color alone for state (pair color with icon/label —
  important for the many status states in §8).
- Keyboard operability for the core learner flow (sign in, start, mute/barge-in, end); visible
  focus states. Note: spacebar is already a barge-in shortcut — preserve or re-map deliberately.
- Screen-reader-friendly live regions for transcript and status changes (politeness levels so
  partial-hypothesis updates don't spam).
- Responsive: the **learner journey** (auth → session → analysis) must work on a narrow/mobile
  viewport; the operator drawer can be desktop-first.
- Audio: a visible, labeled audio element/state for TTS playback; respect autoplay constraints.

## 17. Error / loading / empty-state requirements

Every panel needs all three. Specifics: auth errors inline near the form (never a blank
screen); Google disabled = calm note; grading pending/processing = lightweight progress, not a
dead spinner; insufficient-evidence = guidance; backend/gateway unhealthy = a clear banner that
explains *which* dependency is down and what the user can still do; 401/403 = "session expired,
please sign in again." Error copy must be safe — **no raw tokens, codes, secrets, or stack
traces** surfaced to the learner (safe error codes only).

## 18. Out of scope / do-not-design-yet

Mark anything here as *future* if you reference it: lessons/curriculum browser (schema exists,
no API/UI), teacher/admin/multi-user roles, multi-session concurrency, payments/quotas UI
(a `quota_minutes` field exists but no flow), notifications, the outbox relay (operator-only,
never user-facing), and any "secure/SOC2/production-ready" trust badges (untrue today).

## 19. Constraints for later Claude Code implementation

So the design is actually implementable surgically:
- The frontend is **one large protected file** (`services/core-api/src/static/index.html`,
  markup + `cc-*` classes + one inline `<script>`). Implementation will be **incremental**, not
  a wholesale rewrite.
- **Preserve existing element IDs, JS function names, and API call contracts** (Appendix A,
  §22) unless a
  change is explicitly approved in design review. Many IDs are wired to behavior
  (`setAuthToken`, `createSession`, `fetchAndShowGrading`, `startGoogleLogin`, etc.).
- **No secret handling in the frontend**; **no JWT in URLs**; Google uses the one-time
  `google_code` exchange; scrub auth params from the URL after handling.
- UI-only changes must require **no DB/RabbitMQ/Redis mutation** and no backend edits.
- Prefer a commit split: (1) structure/markup, (2) styling, (3) behavior wiring, (4)
  tests/static checks (`node --check` on the inline script + browser visual + auth/session
  smoke). The design should be decomposable along those lines.

## 20. Resolved product direction (decisions for v1)

These were open questions in earlier drafts; they are now **decided**. Design to them.

1. **Primary audience — learner-first.** v1 is a learner product with the operator/developer
   surface demoted to a secondary diagnostics drawer (§6, §13). It is not a developer console
   with a nicer skin.
2. **Canonical URL — `http://localhost:8000/control-center`.** Standardize the control center
   on same-origin `:8000` (simplest, best for Google sign-in); treat `:8080` as gateway-only.
   This is also the canonical first-smoke URL for QA.
3. **Lessons/curriculum — omit from the v1 primary UI.** No "practice topics" placeholder is
   shown unless/until a backend lessons API exists; keep it out of the learner happy path
   (still listed as future in §18).
4. **Branding/theme — calm, coaching tone.** Keep the L.U.V.E name; lead with a calm,
   coaching, learner-first treatment over the "industrial console" identity. A lighter theme
   is acceptable as long as status semantics (§15) stay accessible.
5. **Token UX — diagnostics-only.** Bearer-token controls live entirely in the Developer
   diagnostics drawer (§13); no token field appears in the learner flow.
6. **Mobile — learner flow in scope.** The learner journey (auth → session → analysis) must
   work on a narrow/mobile viewport (§16); the operator drawer may remain desktop-first.
7. **Tone — soften toward learner value.** Replace "industrial / telemetry / lab console"
   wording with calm coaching language; retain only enough technical identity for the
   operator drawer.

## 21. Source evidence appendix (files inspected)

- `README.md` — product purpose, status honesty notes, architecture, service table.
- `CLAUDE.md` — working rules, architecture orientation, commands.
- `docs/ai/CLAUDE_CODE_HANDOFF.md` — §D realtime pipeline, §E grading, §L2 observability,
  §L3 STT concurrency (1 session/node), §L4 GPU, §L5 outbox relay (default-off), §L6 Google
  OAuth (paused), §O design/code workflow.
- `docker-compose.yml` — services/ports/profiles, env passthrough (incl. Google, default-off).
- `infrastructure/db-init/01-init.sql` — `users` (incl. `google_sub`, nullable `password_hash`),
  `sessions`, `grading_results`, `lessons` (no API), `session_outbox`.
- `infrastructure/db-migrations/0004_users_google_oauth.sql` — Google identity schema.
- `services/core-api/src/main.py` — :8000 app, `/`, `/readyz`, `/control-center`, `/static`.
- `services/core-api/run_ten.py` — :8080 gateway, `/rtc/offer|ice|cmd`, `/rtc/health`,
  `/healthz`, `/readyz`, `/control-center`.
- `services/core-api/src/api/v1/auth.py` — register/login/me + Google start/callback/exchange,
  disabled-gate 404, one-time code.
- `services/core-api/src/api/v1/sessions.py` — session create/read + grading + grading/status.
- `services/core-api/src/api/v1/stream.py` — legacy `/ws/chat/{session_id}`.
- `services/core-api/src/schemas/session.py` — `SessionRead`, `GradingRead`,
  `GradingStatusRead` (status set, `is_dev_preview`, scores, corrections).
- `services/core-api/src/schemas/auth.py`, `schemas/user.py` — auth payloads, `UserRead`
  (no `password_hash` exposed).
- `services/core-api/src/models/user.py`, `core/config.py`, `services/google_oauth.py`,
  `services/oauth_state_store.py` — user model, settings/gating, OIDC client, Redis one-time code.
- `services/grading-worker/src/worker.py` — fake vs LLM dispatch, provider/grader_version,
  eligibility gate.
- `services/core-api/src/static/index.html` — current 3-view UI, element IDs, status themes,
  realtime/transcript/grading wiring (inventory in §5).

## 22. Appendix A — Claude Code implementation inventory (not design-facing)

This appendix is for the later Claude Code implementation phase, **not** for the designer. It
records the concrete handles in the current `static/index.html` so the spec can be wired
surgically (§19). None of these IDs/strings are UX decisions; they are constraints.

**Existing element IDs to preserve** (unless a change is explicitly approved in design review):
`core-api-url`, `gateway-url`, `session-id`, `last-session-id`, `auth-token`,
`clear-token-btn`, `create-session-btn`, `connect-btn`, `disconnect-btn`, `mute-mic-btn`,
`barge-btn`, `stt-only`, `mute-tts`, `copy-stt-summary-btn`, `subtitle-final`,
`subtitle-partial`, `assistant-meta`, `assistant-stream`, `remote-audio`, `event-log`,
`stt-diagnostics`, `status-monitor` (`status-dot`/`status-text`), `api-status`
(`api-status-dot`/`api-status-text`), `session-grading-card`, `grading-content`,
`pedagogical-zone`, `pedagogical-text`, `offer-endpoint`, `ice-endpoint`, `cmd-endpoint`.

**Current status-theme vocabulary in code:** `statusThemes` = `disconnected`, `thinking`
("AI Thinking"), `ready`, `error`, `llm-error`; `apiStatusThemes` = `idle`, `busy`, `ready`,
`error`. The design's expanded state set (§8) is the target; these are the baseline the
implementation starts from and maps onto real events.

---

*Prepared as a design input only. It introduces no runtime change. Implementation will follow
the §O Design → Code → Review workflow in `docs/ai/CLAUDE_CODE_HANDOFF.md`.*
