import { useState } from "react";

interface AuthScreenProps {
  onBack: () => void;
  onContinue: () => void;
}

type Tab = "login" | "register";

/**
 * Auth screen — STATIC SHELL ONLY. No real auth calls in this skeleton.
 * Fields are presentational; "Continue" navigates to the practice screen.
 * Google sign-in is shown as a disabled/not-configured visual state (matches the
 * paused live-login reality; real exchange is wired in a later phase).
 */
export function AuthScreen({ onBack, onContinue }: AuthScreenProps) {
  const [tab, setTab] = useState<Tab>("login");
  const isRegister = tab === "register";

  return (
    <main className="screen screen--auth">
      <section className="card auth-card">
        <div className="auth-card__head">
          <div>
            <h1 className="auth-card__title">{isRegister ? "Create your account" : "Welcome back"}</h1>
            <p className="auth-card__sub">Sign in to start a speaking session.</p>
          </div>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onBack}>
            ← Back
          </button>
        </div>

        <div className="tabs" role="tablist" aria-label="Sign in or create account">
          <button
            type="button"
            role="tab"
            aria-selected={!isRegister}
            className={`tab ${!isRegister ? "tab--active" : ""}`}
            onClick={() => setTab("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isRegister}
            className={`tab ${isRegister ? "tab--active" : ""}`}
            onClick={() => setTab("register")}
          >
            Create account
          </button>
        </div>

        {/* Static form — preventDefault; no submission logic in the skeleton. */}
        <form className="form" onSubmit={(e) => e.preventDefault()}>
          {isRegister && (
            <label className="field">
              <span className="field__label">Username</span>
              <input className="input" type="text" autoComplete="nickname" placeholder="e.g. alex_lee" />
            </label>
          )}
          <label className="field">
            <span className="field__label">Email</span>
            <input className="input" type="email" autoComplete="username" placeholder="you@example.com" />
          </label>
          <label className="field">
            <span className="field__label">Password</span>
            <input className="input" type="password" autoComplete="current-password" placeholder="••••••••" />
          </label>

          <button type="button" className="btn btn--primary btn--lg btn--block" onClick={onContinue}>
            Continue
          </button>
        </form>

        <div className="divider"><span>or</span></div>

        <button type="button" className="btn btn--ghost btn--block" disabled aria-disabled="true">
          Continue with Google
        </button>
        <p className="auth-card__note">Google sign-in is not configured yet.</p>
      </section>
    </main>
  );
}
