# LUVE Control Center — Claude Design Intake Review

> **Mode:** Design intake / audit only. No implementation, no runtime change.
> **Repo state at review:** HEAD `1cb4035`, `main == origin/main` (0/0), index clean.
> **Design package:** `docs/design/luvedesign/` (untracked, user-placed, 2.7 MB, 33 files).
> **Approved brief:** `docs/design/CLAUDE_DESIGN_CONTROL_CENTER_BRIEF.md` (491 lines).
> **Target frontend:** `services/core-api/src/static/index.html` (single protected file).
>
> This report is the only file created by this task. It modifies neither the design
> package nor `static/index.html`.

---

## 1. Design package inventory

Exported "Project archive" from Claude Design, placed under `docs/design/luvedesign/`.

| Group | Files | Role |
|---|---|---|
| **Written spec** | `LUVE Control Center - Design Spec.html` (92 KB) | **Primary artifact** — full screen-by-screen UX spec |
| Spec styling | `assets/spec.css` (12 KB) | Styles the spec *document* (scrollspy nav). Not app CSS. |
| **Design tokens** | `assets/luve-tokens.css` (5 KB) | Reusable foundation: palette, type, spacing, motion, reduced-motion |
| Prototype shell | `LUVE Practice - Prototype.html` (1.5 KB) | React+Babel CDN loader for the JSX prototype |
| Prototype code | `proto-app.jsx`, `proto-screens.jsx`, `proto-live-analysis.jsx`, `proto-sessions.jsx` (~41 KB) | **React** prototype. Reference only (app is vanilla HTML) |
| Prototype styling | `assets/proto.css` (25 KB) | Prototype CSS incl. cat-mascot layer. Reference only |
| **Cat mascot** | `assets/cat-*.js` (≈1.16 MB), `uploads/cat_*.json` (≈1.12 MB) | Lottie animations: boot splash + floating ambient cat + per-state cats. **~2.3 MB combined** |
| Screenshots | `scratch/*.png`, `uploads/*.png` | Visual exports / pasted refs |
| Scratch | `scratch/qa.html`, `scratch/qa2.html` | QA scratch pages |
| Brief copy | `uploads/CLAUDE_DESIGN_CONTROL_CENTER_BRIEF.md` | **Byte-identical to the approved brief** — confirms the package was built from the refined v1cb4035 brief |
| Metadata | `uploads/ec4b70b4-*.json` | Generator metadata |

No `package.json` / build config — this is an export, not a buildable app.

## 2. Main artifact summary

1. **What is the main design artifact?** `LUVE Control Center - Design Spec.html` — a
   complete, source-grounded written UX specification (title: "LUVE Control Center — Design
   Specification"). It is the Claude Design deliverable the brief's workflow calls for.
2. **Self-contained prototype, multi-file app, or static export?** A **static export with
   two layers**: (a) a self-contained spec HTML document (the deliverable), and (b) a
   separate React/Babel/Lottie *prototype* (`LUVE Practice - Prototype.html` + `.jsx`) that
   renders the screens for visual reference only.
3. **Written spec text or only visual?** **Rich written spec** — 13 screen specs (§3.1–3.13),
   component hierarchy, a first-30-second storyboard, visual-language tokens, an explicit
   "what to avoid" list, a motion/microinteraction spec, accessibility, responsive rules,
   and an "Implementation guidance for Claude Code" section that restates our surgical
   constraints (preserve IDs, two-origin, security invariants, async grading, honesty rule).
4. **Assets/fonts/images to avoid copying blindly?** **Yes.** The Lottie cat mascot
   (`cat-*.js` / `cat_*.json`, ~2.3 MB) and the CDN web fonts (Newsreader, Hanken Grotesk,
   JetBrains Mono via Google Fonts) must not be dropped into the app unconsidered.
5. **Generated code not to productionize directly?** **Yes** — the `.jsx` React prototype,
   `proto.css`, `spec.css`, and the prototype's CDN script tags (React/ReactDOM/Babel-standalone/
   lottie-web from unpkg) are prototype/doc scaffolding, not production code.

## 3. Alignment with the approved brief

The spec is **strongly aligned**. It even embeds the brief's hard constraints verbatim.

| Brief requirement | Spec coverage | Verdict |
|---|---|---|
| Learner-first priority | "turns a single engineering console into a learner-first product"; Open-decisions says learner-vs-console is "settled… not reopened" | ✅ Aligned |
| First-30-second demo path | Dedicated "First-30-second demo storyboard" (landing→sign in→Start practice→speak/listen→end→analysis) | ✅ Aligned |
| Diagnostics hidden by default | "Stays in the diagnostics drawer (never the happy path)"; URLs/token/event-log/endpoints/health all in a right drawer | ✅ Aligned |
| Google disabled / error states | §3.3 dedicated to disabled + `auth_error` mappings | ✅ Aligned |
| Fake / dev-preview grading warning | §3.8 dev-preview screen; `is_dev_preview`/`grader_version` drive the signal | ✅ Aligned |
| Analysis states | §3.6 loading, §3.7 real LLM, §3.8 preview, §3.9 insufficient evidence | ✅ Aligned |
| Live session states | §3.5 + VoiceIndicator: listening · you-speaking · STT-processing · AI-thinking · AI-speaking · interrupted | ✅ Aligned |
| No direct worker-health probe | "grading-stall hint inferred from repeated pending/processing — do not add a worker-health probe" | ✅ Aligned |
| No invented lessons/curriculum primary UI | Listed in spec "Out of scope (future, per brief §18)" | ✅ Aligned |
| Token / API-URL controls diagnostics-only | Explicitly drawer-only | ✅ Aligned |
| Mobile learner flow | §3.11 mobile flow + responsive ≤719px sticky control bar | ✅ Aligned |
| Calm/coaching/professional visual direction | Warm paper palette, single petrol-teal brand, editorial serif; "what to avoid" bans neon/gradients/AI-sparkle | ✅ Aligned |
| Bounded microinteractions + reduced motion | §07 motion spec; mic indicator + skeletons the only "alive" motion; `prefers-reduced-motion` fallbacks | ✅ Aligned (see §4 deviation re: cat) |
| Honesty / no fake UI | Explicit "Honesty constraint (carry into code)" | ✅ Aligned |

## 4. Deviations / unsupported / invented items

1. **Cat mascot (decorative looping animation) — internal contradiction + repo/perf risk.**
   The prototype ships a fixed-position floating Lottie cat ("ambient", behind content) plus a
   boot splash and per-state cat animations. This **contradicts the brief** ("no decorative
   'AI sparkle' noise", "no looping background animation") *and the spec's own "what to avoid"
   list*, which bans "looping background animation". The animation payload is **~2.3 MB**
   (`cat-ok-data.js` alone is 817 KB). **Recommendation: OMIT from v1.** If the user wants a
   delight element later, it would be a separate, off-by-default, reduced-motion-gated,
   lazy-loaded decision — not part of the surgical restyle.

2. **Session History (§3.13) assumes a backend `GET /sessions` list endpoint that does not
   exist.** Current `sessions.py` exposes only `POST ""`, `GET /{id}`, `GET /{id}/grading`,
   `GET /{id}/grading/status` — **no list route**. The spec itself flags this as "the one
   additive backend capability to greenlight." **Defer**: do not build the history list or the
   `SessionHistory` component until a backend endpoint is approved and added.

3. **External CDN dependencies (prototype only).** The prototype loads React/ReactDOM/Babel-
   standalone/lottie-web from unpkg and fonts from Google Fonts. These are **prototype
   scaffolding** and must not enter the production single-file app (render-blocking, offline/
   privacy concerns). Fonts, if adopted, should be a deliberate self-host-vs-fallback decision.

4. **Spec header cites stale HEAD `6fa9665` / "Draft for review".** Cosmetic only; the
   embedded brief copy is byte-identical to current `1cb4035`, so content is in sync.

**Missing required states:** none material — the spec covers the full §8 state matrix
(auth, realtime, grading, system-health, responsive) including define-but-dormant ones.

**Debug-console risk:** low. The spec deliberately moves all operator readouts into the
drawer and leads with editorial/learner surfaces. The only thing that would *re-introduce*
console feel is leaking drawer content (URLs/token/logs) onto the happy path during a sloppy
re-parent — a Phase-2 implementation risk, not a spec defect.

## 4a. User decisions before implementation

The two gates raised in §4 and §10 have been **decided by the user (2026-06-05)**. They are
binding on the implementation phase.

### Decision 1 — Cat mascot / Lottie assets: **OMIT from v1**

- **Decision:** Omit the cat mascot from the v1 implementation entirely.
- **Reason:** It is a decorative, looping animation that conflicts with the clean,
  professional, learner-first direction; it contradicts the design package's own "what to
  avoid" guidance (which explicitly bans "looping background animation"); and it adds
  ~2.3 MB of asset bloat (`cat-*.js` + `cat_*.json`).
- **Handling:** Keep the cat assets in the design package as **reference only**. Do **not**
  copy cat assets, cat JS (`cat-boot.js`/`cat-float.js`/`cat-*-data.js`), Lottie JSON
  (`cat_*.json`), or the ambient/boot mascot behavior into the production frontend. The
  `#cat-layer` / `#cat-boot` constructs from `luve-tokens.css`/`proto.css` are not ported.
- **Future:** May be reconsidered later **only** as an optional, explicitly user-approved
  brand element, gated behind `prefers-reduced-motion`, lazy-loaded, and held to a strict
  performance budget. Not part of any v1 commit.

### Decision 2 — Session History / Past sessions: **DEFER from v1**

- **Decision:** Defer the Session History (§3.13) / Past-sessions feature from the v1
  implementation.
- **Reason:** The current backend has **no `GET /sessions` list endpoint** — only
  session create (`POST ""`), session-by-id (`GET /{id}`), and grading surfaces
  (`GET /{id}/grading[/status]`) exist. Building a history list would require inventing data
  the backend cannot supply.
- **Handling:** Do **not** add a Past-sessions UI that pretends a list of prior sessions
  exists. A small "recent session" / "last session analysis" affordance **may** reuse the
  existing last-session state already present in the frontend (`last-session-id`) — but
  **no full history list, no `SessionHistory` component**.
- **Future:** Implement only after a backend `GET /sessions` endpoint plus its
  pagination / empty / error semantics are designed and reviewed as a separate authorized
  task.

## 5. Mapping to current `static/index.html`

Current structure (verified handles, with line numbers): three body-class views
`view-landing` (25) / `view-auth` (99) / `view-app` (148); app sections
`cc-sec-checklist` (298), `cc-sec-session` (156), `cc-sec-controls` (214),
`cc-sec-diagnostics` (336), `cc-sec-insights` (278).

| # | Question | Mapping |
|---|---|---|
| 1 | Screens → existing views | Landing §3.1 → `view-landing`; Auth §3.2 + Google §3.3 → `view-auth`; Home §3.4 / Live §3.5 / Analysis §3.6–3.9 / Diagnostics §3.12 → `view-app` (re-parented) |
| 2 | Elements/functions to **preserve** | IDs `auth-token`, `core-api-url`, `gateway-url`, `create-session-btn`, `connect-btn`, `disconnect-btn`, `mute-mic-btn`, `barge-btn`, `google-login-btn`, `load-grading-btn`, `session-grading-card`, `event-log`, `stt-diagnostics` + JS `setAuthToken`, `createSession`, `fetchAndShowGrading`, `startGoogleLogin` (per brief Appendix A / spec "Preserve unchanged") |
| 3 | Dev controls → **drawer** | `core-api-url`, `gateway-url`, `auth-token` (paste/clear), `event-log`, `stt-diagnostics`, realtime endpoints, provider/grader metadata, health/readiness, demo-build note |
| 4 | Markup/CSS-only components | Layout shell + TopBar, drawer scaffold, landing/auth/home restyle, status chips, score cards, analysis skeletons, typography/palette — re-skin via token CSS vars |
| 5 | Behavior changes (JS wiring, existing events only) | Drawer open/close (focus-trap/ESC), Start-practice CTA → `createSession`+connect, voice-indicator state mapping onto existing STT/LLM/TTS events, grading skeleton/poll reuse of `load-grading-btn`, expanded status vocabulary onto the 6-state palette |
| 6 | **Backend-gated → defer** | Session History §3.13 (`GET /sessions`); any pronunciation-always-present assumption (stays nullable) |
| 7 | **Visual reference only** | All `.jsx`, `proto.css`, `spec.css`, cat mascot, CDN React/Babel/Lottie, Google-Fonts CDN, screenshots |

**Rewrite vs surgical:** surgical is the correct and safer path and the spec is explicitly
written for it ("re-skin and re-parent the DOM; keep the handles"). A wholesale rewrite of the
single protected file is **not** justified — it would risk every wired ID/handler at once with
no incremental rollback. Recommend incremental commits (§7).

## 6. Readiness classification

| Item | Class | Reason / risk / handling |
|---|---|---|
| Design tokens (`luve-tokens.css`) | **Ready** | Hand-port token vars into the app's CSS; low risk; do not `@import` Google Fonts CDN blindly |
| Layout shell + drawer scaffold (Phase 1) | **Ready** | Markup re-parent, no behavior change; risk = breaking IDs → preserve them |
| Drawer-only diagnostics (Phase 2) | **Ready** | Move existing controls; risk = hiding too far → gear entry, focus-trap, ESC |
| Landing/auth/home/analysis restyle | **Ready** | CSS + minimal markup; reference screenshots, not prototype HTML |
| Voice-indicator states | **Ready (wire to existing events)** | Map to current STT/LLM/TTS signals; dormant states stay inert |
| Live layout emphasis (indicator- vs transcript-centered) | **Needs decision** | Spec recommends indicator-centered; user call |
| Practice settings visibility | **Needs decision** | Spec recommends collapsed disclosure on home |
| Theme (light-only vs dark drawer) | **Needs decision** | Spec recommends light-only v1 |
| Post-session navigation (auto-advance vs interstitial) | **Needs decision** | Spec recommends auto-advance + skeletons |
| Corrections depth / pronunciation placement | **Needs decision (needs real payload)** | Tune against a real grading result |
| Session History §3.13 | **Needs backend** | `GET /sessions` does not exist → greenlight + build endpoint first, else defer |
| Cat mascot / Lottie | **Omit (v1)** | Contradicts brief + spec "avoid"; ~2.3 MB bloat; revisit as separate opt-in later |
| `.jsx` / `proto.css` / `spec.css` / CDN libs | **Reference only** | Architecture mismatch (React vs vanilla single file); never copy into app |

## 7. Proposed implementation phases (surgical, small commits)

Mirrors the brief §19 and the spec's "Suggested commit phases." Each is independently
revertable. **Hot path (VAD/STT/LLM/TTS/WebRTC), backend, auth, grading logic, RabbitMQ,
DB, `.env`, and `docker-compose.gpu.local.yml` are untouched in every phase.**

| Phase | Intent | Files likely touched | Risk | Verify | Must NOT touch |
|---|---|---|---|---|---|
| **1. Layout/IA shell** | TopBar + view containers + drawer scaffold; re-parent controls. No behavior change. | `static/index.html`, `static/styles.css` | Med (DOM re-parent can orphan handlers) | `node --check` inline script; load `/control-center`; auth+session smoke | element IDs, JS fn names, API calls |
| **2. Diagnostics → drawer** | Move URLs/token/event-log/STT/health into collapsed drawer (gear, focus-trap, ESC) | same | Med (hide-too-far) | drawer open/close; token paste/clear still works; logs still populate | token-in-URL rule, no secret handling |
| **3. Learner happy path restyle** | Landing/auth/home/Start-practice via tokens | same | Low | visual pass; Google disabled note; login/register | auth.py, request contracts |
| **4. Live workspace restyle** | Voice indicator (listening/speaking/thinking/TTS), two-tier transcript | same | Med (state mapping) | live session; barge-in (spacebar); mute→FLUSH | realtime hot path, gateway code |
| **5. Analysis + preview warning** | Score cards, summary, corrections, `is_dev_preview` banner, skeleton/poll | same | Low | grading pending→graded; preview vs real; insufficient-evidence | grading-worker, schemas |
| **6. Bounded microinteractions** | §07 motion + `prefers-reduced-motion` | `styles.css` (+ small JS) | Low | reduced-motion on/off; no looping bg anim | no cat mascot, no CDN libs |
| **7. Browser verification + cleanup** | Static checks + smoke + remove orphaned CSS/IDs from *these* changes only | same | Low | `node --check`; full happy-path; mobile viewport | unrelated dead code |

## 8. Verification plan

Per phase, non-destructive, no full suite:

- **Static:** extract inline `<script>` and `node --check`; `venv/bin/python -m py_compile`
  is **not** needed (no Python touched).
- **Import smoke (sanity that serving path is intact):**
  `venv/bin/python -c "from src.main import app; print(app.title)"`.
- **Manual browser** at `http://localhost:8000/control-center` (canonical, per brief §20):
  landing → register/login → Google-disabled note → Start practice → live (mic mute, spacebar
  barge-in, End) → analysis loading → graded vs dev-preview → insufficient-evidence.
- **Drawer:** open via gear, ESC closes, focus-trapped; token paste/clear; event log + STT
  diagnostics still populate; editable URLs still effective.
- **Mobile:** narrow viewport learner flow; sticky bottom Mute/End ≥44px.
- **Accessibility:** focus rings; `aria-live="polite"` on phase/connection, partials not
  announced; color+icon+label on every status.
- **Regression guard:** auth + session-create + grading-fetch behave exactly as before.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Prototype-copy** (dropping `.jsx`/React into a vanilla single-file app) | Treat `.jsx`/`proto.css` as reference only; hand-author vanilla markup/CSS |
| **Generated CSS bloat** (`proto.css` 25 KB, `spec.css` 12 KB) | Port only needed token vars from `luve-tokens.css`; do not paste prototype CSS |
| **Cat mascot bloat/perf** (~2.3 MB Lottie + lottie-web CDN) | Omit for v1; if ever added: opt-in, lazy, reduced-motion-gated, self-hosted |
| **Tailwind/class mismatch** (current util + `cc-*` + `styles.css` vs token vars) | Add a token layer; map `cc-*` and `statusThemes` onto the 6-state palette; avoid class collisions |
| **Broken IDs/functions** on re-parent | Preserve all IDs/handlers (brief Appendix A); re-skin, don't rename; `node --check` each phase |
| **Auth/session regression** | UI-only; no backend/auth/grading edits; smoke each phase |
| **Token leakage** | No JWT in URL; token controls drawer-only; scrub Google `google_code` after exchange |
| **Diagnostics hidden too far** | Drawer reachable via gear, focus-trapped, ESC; operators keep full visibility |
| **Mobile complexity** | Reuse spec's simple pattern (mic indicator + transcript + sticky control bar); desktop-first drawer |
| **Unsupported states shown** | Honesty rule: render a state only when a real event/probe backs it; others define-but-dormant |
| **Excessive animation** | Bounded per §07; mic indicator + skeletons only; static reduced-motion fallback |
| **Fonts licensing/bloat** | Newsreader/Hanken/JetBrains Mono are open (OFL) but decide self-host vs system-font fallback; avoid CDN render-block |
| **Inline CSS/JS perf** | Single-file app already large; keep additions lean; no 800 KB assets, no CDN runtime |

## 10. Recommended next step

The Claude Design deliverable (the written spec) is **accepted as well-aligned and
implementation-ready**. Both gates are now resolved (§4a): **cat mascot omitted for v1** and
**Session History deferred for v1**. The spec's remaining "Open design decisions" (live-layout
emphasis, practice-settings visibility, theme, post-session navigation, corrections depth,
pronunciation placement) are non-blocking and can be tuned during the build.

Proceed to **Phase 1 — layout / IA shell** as a surgical, behavior-preserving commit against
`static/index.html`, following the documented Design → Code → Review workflow. Phase 1 scope:

- layout / IA shell
- TopBar (identity + condensed health + diagnostics entry)
- learner-first home (with the primary **Start practice** CTA)
- live-session and analysis view containers
- diagnostics drawer scaffold (collapsed; controls re-parented in a later phase)
- **no cat mascot**
- **no session history list**
- **no backend changes**, no hot-path, no `.env`, preserve all element IDs / JS handles

Subsequent phases follow §7 (diagnostics-drawer wiring → happy-path restyle → live workspace →
analysis/preview → bounded microinteractions → browser verification).

---

*Prepared as an audit/intake artifact only. No runtime change. No files staged, committed, or
pushed; the design package and `static/index.html` are unmodified.*
