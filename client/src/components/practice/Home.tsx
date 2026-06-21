import { useState } from "react";
import { useUiLanguage } from "../../lib/uiLanguage";
import { CatCompanion } from "../CatCompanion";

interface Settings {
  sttOnly: boolean;
  muteTts: boolean;
}

interface HomeProps {
  userName: string;
  onStart: () => void;
  starting?: boolean;
  startError?: string | null;
  settings: Settings;
  setSettings: (s: Settings) => void;
}

/** Authenticated home — primary "Start practice" + a quiet practice-settings disclosure. */
export function Home({
  userName,
  onStart,
  starting = false,
  startError = null,
  settings,
  setSettings,
}: HomeProps) {
  const [open, setOpen] = useState(false);
  const { t } = useUiLanguage();
  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-home">
          <div className="p-homecat">
            <CatCompanion variant="idle" size={72} />
          </div>
          <div
            className="p-eyebrow"
            style={{ color: "var(--ink-3)", letterSpacing: ".04em", textTransform: "none", fontSize: "var(--t-sm)" }}
          >
            {t("home.welcome", { name: userName })}
          </div>
          <h2>{t("home.h2")}</h2>
          <p>{t("home.lead")}</p>
          <button className="btn btn--primary btn--xl" onClick={onStart} disabled={starting}>
            {starting ? t("home.starting") : t("home.start")}
          </button>
          {startError && (
            <p className="p-note" style={{ color: "var(--err-ink)", marginTop: "14px" }} role="alert">
              {startError}
            </p>
          )}

          <div className="p-settings">
            <button className="p-disclosure" aria-expanded={open} onClick={() => setOpen(!open)}>
              <span style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }}>⌄</span>{" "}
              {t("home.settings")}
              <span style={{ color: "var(--hairline-2)" }}>·</span>{" "}
              <span style={{ color: "var(--ink-4)" }}>{t("home.oneSession")}</span>
            </button>
            {open && (
              <div className="p-settings__body">
                <div className="p-toggle-row">
                  <div className="lbl">
                    <b>{t("home.transcriptOnly")}</b>
                    <span>{t("home.transcriptOnlyDesc")}</span>
                  </div>
                  <button
                    className={"p-switch" + (settings.sttOnly ? " on" : "")}
                    aria-pressed={settings.sttOnly}
                    aria-label={t("home.transcriptOnly")}
                    onClick={() => setSettings({ ...settings, sttOnly: !settings.sttOnly })}
                  />
                </div>
                <div className="p-toggle-row">
                  <div className="lbl">
                    <b>{t("home.muteTutor")}</b>
                    <span>{t("home.muteTutorDesc")}</span>
                  </div>
                  <button
                    className={"p-switch" + (settings.muteTts ? " on" : "")}
                    aria-pressed={settings.muteTts}
                    aria-label={t("home.muteTutor")}
                    onClick={() => setSettings({ ...settings, muteTts: !settings.muteTts })}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
