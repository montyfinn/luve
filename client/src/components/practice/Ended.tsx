import { useUiLanguage } from "../../lib/uiLanguage";

/** Brief "reviewing your conversation" confirmation between live and analysis.
 *  (Cat/Lottie deferred — CSS spinner stand-in.) */
export function Ended() {
  const { t } = useUiLanguage();
  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-ended">
          <div className="p-spinner p-spinner--sm" style={{ margin: "0 auto" }} />
          <h2>{t("ended.h2")}</h2>
          <p>{t("ended.body")}</p>
        </div>
      </div>
    </div>
  );
}
