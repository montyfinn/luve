import { useState } from "react";
import { BackIcon, CloseIcon } from "./icons";

type Mode = "login" | "register";

interface AuthScreenProps {
  mode: Mode;
  setMode: (m: Mode) => void;
  googleEnabled: boolean;
  onSubmit: (name: string) => void; // mock — navigates to practice
  onGoogle: () => void; // mock — logs + (if enabled) navigates
  onBack: () => void;
}

/**
 * Auth — STATIC SHELL ONLY. Validation is client-side cosmetic; onSubmit just
 * advances the mock flow. Google is shown enabled/disabled per the diagnostics
 * "Demo controls" toggle (default disabled = the paused live-login reality).
 */
export function AuthScreen({ mode, setMode, googleEnabled, onSubmit, onGoogle, onBack }: AuthScreenProps) {
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [uname, setUname] = useState("");
  const [err, setErr] = useState("");

  function submit() {
    if (!email.trim() || pwd.length < 1) {
      setErr("That email or password doesn't match. Try again.");
      return;
    }
    if (mode === "register" && uname.trim().length < 3) {
      setErr("Choose a username with at least 3 characters.");
      return;
    }
    setErr("");
    onSubmit(mode === "register" ? uname : "there");
  }

  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-card p-authcard">
          <button
            className="p-linkbtn"
            onClick={onBack}
            style={{ marginBottom: "12px", marginLeft: "-8px", display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            <BackIcon size={15} /> Back
          </button>

          <div className="p-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={mode === "login"}
              className={"p-tab" + (mode === "login" ? " is-active" : "")}
              onClick={() => { setMode("login"); setErr(""); }}
            >
              Sign in
            </button>
            <button
              role="tab"
              aria-selected={mode === "register"}
              className={"p-tab" + (mode === "register" ? " is-active" : "")}
              onClick={() => { setMode("register"); setErr(""); }}
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
            />
            {err && (
              <div className="p-inline-err" id="p-autherr">
                <CloseIcon size={14} stroke="var(--err)" /> {err}
              </div>
            )}
          </div>

          <button className="btn btn--primary btn--full" onClick={submit}>
            {mode === "login" ? "Sign in" : "Create account"}
          </button>

          <div className="p-divider">or</div>

          <button className="p-google" onClick={onGoogle} disabled={!googleEnabled}>
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
