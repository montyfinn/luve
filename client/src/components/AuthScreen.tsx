import { useState } from "react";
import { BackIcon, CloseIcon } from "./icons";

type Mode = "login" | "register";

export interface AuthCreds {
  username: string;
  email: string;
  password: string;
}

interface AuthScreenProps {
  mode: Mode;
  setMode: (m: Mode) => void;
  googleEnabled: boolean;
  /** Real auth — throws ApiError on failure; resolves (and App navigates) on success. */
  onSubmit: (mode: Mode, creds: AuthCreds) => Promise<void>;
  onGoogle: () => void; // mock only — never calls Google in C4
  onBack: () => void;
}

/**
 * Auth — now wired to real core_api email/password auth via onSubmit.
 * Validation mirrors the backend (username ≥3, password ≥8). Server errors are
 * shown inline in the existing design. Google stays mock/disabled (C4 scope).
 */
export function AuthScreen({ mode, setMode, googleEnabled, onSubmit, onGoogle, onBack }: AuthScreenProps) {
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [uname, setUname] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function switchMode(m: Mode) {
    setMode(m);
    setErr("");
  }

  async function submit() {
    if (busy) return;
    if (!email.trim()) {
      setErr("Enter your email address.");
      return;
    }
    if (pwd.length < 8) {
      setErr("Password must be at least 8 characters.");
      return;
    }
    if (mode === "register" && uname.trim().length < 3) {
      setErr("Choose a username with at least 3 characters.");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      await onSubmit(mode, { username: uname.trim(), email: email.trim(), password: pwd });
      // success: App navigates away; this component unmounts.
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-card p-authcard">
          <button
            className="p-linkbtn"
            onClick={onBack}
            disabled={busy}
            style={{ marginBottom: "12px", marginLeft: "-8px", display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            <BackIcon size={15} /> Back
          </button>

          <div className="p-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={mode === "login"}
              className={"p-tab" + (mode === "login" ? " is-active" : "")}
              onClick={() => switchMode("login")}
              disabled={busy}
            >
              Sign in
            </button>
            <button
              role="tab"
              aria-selected={mode === "register"}
              className={"p-tab" + (mode === "register" ? " is-active" : "")}
              onClick={() => switchMode("register")}
              disabled={busy}
            >
              Create account
            </button>
          </div>

          {mode === "register" && (
            <div className="p-field">
              <label htmlFor="p-uname">Username</label>
              <input
                id="p-uname"
                className="p-input"
                value={uname}
                onChange={(e) => setUname(e.target.value)}
                placeholder="At least 3 characters"
                disabled={busy}
              />
            </div>
          )}
          <div className="p-field">
            <label htmlFor="p-email">Email</label>
            <input
              id="p-email"
              className="p-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              placeholder="you@example.com"
              disabled={busy}
            />
          </div>
          <div className="p-field">
            <label htmlFor="p-pwd">Password</label>
            <input
              id="p-pwd"
              className={"p-input" + (err ? " is-error" : "")}
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              type="password"
              placeholder={mode === "register" ? "At least 8 characters" : "••••••••"}
              aria-describedby={err ? "p-autherr" : undefined}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              disabled={busy}
            />
            {err && (
              <div className="p-inline-err" id="p-autherr">
                <CloseIcon size={14} stroke="var(--err)" /> {err}
              </div>
            )}
          </div>

          <button className="btn btn--primary btn--full" onClick={submit} disabled={busy}>
            {busy
              ? mode === "login"
                ? "Signing in…"
                : "Creating account…"
              : mode === "login"
                ? "Sign in"
                : "Create account"}
          </button>

          <div className="p-divider">or</div>

          <button className="p-google" onClick={onGoogle} disabled={!googleEnabled || busy}>
            <span className={"p-gmark" + (googleEnabled ? "" : " p-gmark--off")} />
            Continue with Google
          </button>
          {!googleEnabled && (
            <p className="p-note">
              Google sign-in isn't set up on this build yet — use your email and password.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
