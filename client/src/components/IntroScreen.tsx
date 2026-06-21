import { useUiLanguage } from "../lib/uiLanguage";

interface IntroScreenProps {
  onStart: () => void; // -> auth (register intent)
  onLogin: () => void; // -> auth (login intent)
}

/** Landing — two-column hero with editorial headline + "how it works" card. */
export function IntroScreen({ onStart, onLogin }: IntroScreenProps) {
  const { t } = useUiLanguage();
  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-hero">
          <div>
            <p className="p-eyebrow">{t("intro.eyebrow")}</p>
            <h1>
              {t("intro.h1a")} <em>{t("intro.h1em")}</em>
            </h1>
            <p>{t("intro.lead")}</p>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <button className="btn btn--primary" onClick={onStart}>
                {t("intro.start")}
              </button>
              <button className="btn btn--ghost" onClick={onLogin}>
                {t("intro.haveAccount")}
              </button>
            </div>
            <p className="p-note" style={{ marginTop: "24px" }}>
              {t("intro.note")}
            </p>
          </div>
          <div className="p-card p-howcard">
            <p className="p-eyebrow" style={{ marginBottom: "18px" }}>
              {t("intro.how")}
            </p>
            <div className="p-howstep">
              <span className="num">1</span>
              <div>
                <div style={{ fontWeight: 600 }}>{t("intro.step1")}</div>
                <div style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>{t("intro.step1d")}</div>
              </div>
            </div>
            <div className="p-howstep">
              <span className="num">2</span>
              <div>
                <div style={{ fontWeight: 600 }}>{t("intro.step2")}</div>
                <div style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>{t("intro.step2d")}</div>
              </div>
            </div>
            <div className="p-howstep">
              <span className="num">3</span>
              <div>
                <div style={{ fontWeight: 600 }}>{t("intro.step3")}</div>
                <div style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)" }}>{t("intro.step3d")}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
