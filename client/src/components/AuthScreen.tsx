import { useState } from "react";
import { useUiLanguage } from "../lib/uiLanguage";
import { CatCompanion } from "./CatCompanion";
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
  onGoogle: () => void; // disabled in this build — never calls Google
  onBack: () => void;
}

/**
 * Auth — now wired to real core_api email/password auth via onSubmit.
 * Validation mirrors the backend (username ≥3, password ≥8). Server errors are
 * shown inline in the existing design. Google sign-in stays disabled.
 */
export function AuthScreen({ mode, setMode, googleEnabled, onSubmit, onGoogle, onBack }: AuthScreenProps) {
  const { t } = useUiLanguage();
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
      setErr(t("auth.errEmail"));
      return;
    }
    if (pwd.length < 8) {
      setErr(t("auth.errPwd"));
      return;
    }
    if (mode === "register" && uname.trim().length < 3) {
      setErr(t("auth.errUname"));
      return;
    }
    setErr("");
    setBusy(true);
    try {
      await onSubmit(mode, { username: uname.trim(), email: email.trim(), password: pwd });
      // success: App navigates away; this component unmounts.
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("auth.errGeneric"));
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
            <BackIcon size={15} /> {t("auth.back")}
          </button>

          <div className="p-authcat">
            <CatCompanion variant="curious" size={54} />
          </div>

          <div className="p-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={mode === "login"}
              className={"p-tab" + (mode === "login" ? " is-active" : "")}
              onClick={() => switchMode("login")}
              disabled={busy}
            >
              {t("auth.signIn")}
            </button>
            <button
              role="tab"
              aria-selected={mode === "register"}
              className={"p-tab" + (mode === "register" ? " is-active" : "")}
              onClick={() => switchMode("register")}
              disabled={busy}
            >
              {t("auth.createAccount")}
            </button>
          </div>

          {mode === "register" && (
            <div className="p-field">
              <label htmlFor="p-uname">{t("auth.username")}</label>
              <input
                id="p-uname"
                className="p-input"
                value={uname}
                onChange={(e) => setUname(e.target.value)}
                placeholder={t("auth.usernamePh")}
                disabled={busy}
              />
            </div>
          )}
          <div className="p-field">
            <label htmlFor="p-email">{t("auth.email")}</label>
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
            <label htmlFor="p-pwd">{t("auth.password")}</label>
            <input
              id="p-pwd"
              className={"p-input" + (err ? " is-error" : "")}
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              type="password"
              placeholder={mode === "register" ? t("auth.passwordPh") : "••••••••"}
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
                ? t("auth.signingIn")
                : t("auth.creatingAccount")
              : mode === "login"
                ? t("auth.signIn")
                : t("auth.createAccount")}
          </button>

          <div className="p-divider">{t("auth.or")}</div>

          <button className="p-google" onClick={onGoogle} disabled={!googleEnabled || busy}>
            <span className={"p-gmark" + (googleEnabled ? "" : " p-gmark--off")} />
            {t("auth.google")}
          </button>
          {!googleEnabled && <p className="p-note">{t("auth.googleNote")}</p>}
        </div>
      </div>
    </div>
  );
}
