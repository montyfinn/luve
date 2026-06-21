import { useState } from "react";
import type { SessionGradingResult, SessionGradingStatus } from "../../lib/gradingApi";
import type { SessionHistoryItem } from "../../lib/sessionApi";
import { useUiLanguage } from "../../lib/uiLanguage";

type Status = "loading" | "pending" | "ready" | "insufficient" | "failed" | "unavailable" | "history";

interface AnalysisProps {
  status: Status;
  grading: SessionGradingResult | null;
  gradingStatus?: SessionGradingStatus | null;
  gradingError?: string | null;
  historySession?: SessionHistoryItem | null;
  onAgain: () => void;
  onHistory: () => void;
  onRefreshGrading?: () => void;
}

function ScoreCard({ k, v, overall }: { k: string; v: number; overall?: boolean }) {
  return (
    <div className={"p-score" + (overall ? " overall" : "")}>
      <div className="p-score__k">{k}</div>
      <div className="p-score__v">{Number.isInteger(v) ? v : v.toFixed(1)}</div>
      <div className="p-score__o">/ 10</div>
    </div>
  );
}

function formatSessionTime(value: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatStatus(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function compactNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { notation: value >= 1000 ? "compact" : "standard" }).format(value);
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-history-metric">
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

function HistorySummaryBanner({ session }: { session?: SessionHistoryItem | null }) {
  const { t } = useUiLanguage();
  if (!session) return null;
  return (
    <div className="p-history-summary">
      <div>
        <strong>{t("analysis.selectedPast")}</strong>
        <p>
          {formatSessionTime(session.started_at)} · {formatStatus(session.status)}
        </p>
      </div>
      <div className="p-history-metrics p-history-metrics--mini">
        <SummaryMetric label={t("analysis.metricEnded")} value={formatSessionTime(session.ended_at)} />
        <SummaryMetric label={t("analysis.metricTokens")} value={compactNumber(session.total_tokens)} />
        <SummaryMetric label={t("analysis.metricStops")} value={String(session.manual_stops_count)} />
      </div>
    </div>
  );
}

function readableReason(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(/[_-]+/g, " ");
}

function correctionText(item: Record<string, unknown>): string {
  const message = item.message;
  if (typeof message === "string" && message.trim()) return message.trim();
  const original = item.original;
  const corrected = item.corrected ?? item.correction;
  if (typeof original === "string" && typeof corrected === "string") {
    return `${original} → ${corrected}`;
  }
  const type = item.type;
  if (typeof type === "string" && type.trim()) return readableReason(type);
  return "Correction detail available.";
}

function skillLabel(item: Record<string, unknown>): string {
  return readableReason(typeof item.skill === "string" ? item.skill : "skill");
}

function skillScore(item: Record<string, unknown>): string | null {
  const score = item.score;
  return typeof score === "number" ? `${Number.isInteger(score) ? score : score.toFixed(1)}/10` : null;
}

function safeJson(value: Record<string, unknown>): string {
  const keys = Object.keys(value);
  if (keys.length === 0) return "{}";
  return JSON.stringify(value, null, 2);
}

/** Session analysis — loading (skeletons), insufficient-evidence, or graded.
 *  Current and selected-history grading both use the authenticated grading API.
 *  Transcript replay stays deferred because the history endpoint is intentionally lean. */
export function Analysis({
  status,
  grading,
  gradingStatus,
  gradingError,
  historySession,
  onAgain,
  onHistory,
  onRefreshGrading,
}: AnalysisProps) {
  const { t } = useUiLanguage();
  const [showDetails, setShowDetails] = useState(false);

  if (status === "loading") {
    return (
      <div className="p-view p-main">
        <div className="p-wrap">
          <div className="p-analysis">
            <div className="p-analysis__head">
              <h2>{historySession ? t("analysis.titleSaved") : t("analysis.titleYours")}</h2>
              <span className="p-chip p-chip--busy">
                <span className="d" />
                {t("analysis.chipLoading")}
              </span>
            </div>
            <HistorySummaryBanner session={historySession} />
            <p style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)", margin: "0 0 14px" }}>
              {t("analysis.loadingHint")}
            </p>
            <div className="p-scores">
              <div className="p-skel p-skel--card" />
              <div className="p-skel p-skel--card" />
              <div className="p-skel p-skel--card" />
              <div className="p-skel p-skel--card" />
            </div>
            <div className="p-panel">
              <div className="p-skel p-skel--line" style={{ width: "30%" }} />
              <div className="p-skel p-skel--line" style={{ width: "92%" }} />
              <div className="p-skel p-skel--line" style={{ width: "84%" }} />
              <div className="p-skel p-skel--line" style={{ width: "70%", marginBottom: 0 }} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "pending") {
    const label = gradingStatus?.status === "processing" ? t("analysis.pendingRunning") : t("analysis.pendingQueued");
    return (
      <div className="p-view p-main">
        <div className="p-wrap p-center">
          <div className="p-analysis">
            <HistorySummaryBanner session={historySession} />
            <div className="p-panel p-evidence">
              <div className="p-spinner p-spinner--sm" style={{ margin: "0 auto 14px" }} />
              <h3>{label}</h3>
              <p>{t("analysis.pendingBody")}</p>
              {gradingStatus?.student_word_count != null && (
                <p className="p-note">
                  {t("analysis.detectedWords")}: {gradingStatus.student_word_count}
                </p>
              )}
              <div className="p-analysis__actions" style={{ justifyContent: "center" }}>
                {onRefreshGrading && (
                  <button className="btn btn--primary" onClick={onRefreshGrading}>
                    {t("analysis.checkAgain")}
                  </button>
                )}
                <button className="btn btn--ghost" onClick={onHistory}>
                  {t("analysis.pastSessions")}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "insufficient") {
    const reason = readableReason(gradingStatus?.reason);
    return (
      <div className="p-view p-main">
        <div className="p-wrap p-center">
          <div className="p-analysis">
            <HistorySummaryBanner session={historySession} />
            <div className="p-panel p-evidence">
              <div className="em">🌱</div>
              <h3>{t("analysis.insufficientTitle")}</h3>
              <p>{t("analysis.insufficientBody")}</p>
              {gradingStatus?.student_word_count != null && (
                <p className="p-note">
                  {t("analysis.detectedWords")}: {gradingStatus.student_word_count}
                </p>
              )}
              {reason && (
                <p className="p-note">
                  {t("analysis.reason")}: {reason}
                </p>
              )}
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                <button className="btn btn--primary" onClick={onAgain}>
                  {t("analysis.tryLonger")}
                </button>
                <button className="btn btn--ghost" onClick={onHistory}>
                  {t("analysis.pastSessions")}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "failed" || status === "unavailable") {
    return (
      <div className="p-view p-main">
        <div className="p-wrap p-center">
          <div className="p-analysis">
            <HistorySummaryBanner session={historySession} />
            <div className="p-panel p-evidence">
              <div className="em">!</div>
              <h3>{status === "failed" ? t("analysis.failedTitle") : t("analysis.unavailableTitle")}</h3>
              <p>{gradingError || t("analysis.unavailableBody")}</p>
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                {onRefreshGrading && (
                  <button className="btn btn--primary" onClick={onRefreshGrading}>
                    {t("analysis.retry")}
                  </button>
                )}
                <button className="btn btn--ghost" onClick={onAgain}>
                  {t("analysis.practiceAgain")}
                </button>
                <button className="btn btn--ghost" onClick={onHistory}>
                  {t("analysis.pastSessions")}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "history" && historySession) {
    return (
      <div className="p-view p-main">
        <div className="p-wrap">
          <div className="p-analysis">
            <div className="p-analysis__head">
              <div>
                <h2>{t("analysis.titleSummary")}</h2>
                <p className="p-analysis__cap">
                  {formatSessionTime(historySession.started_at)} · {formatStatus(historySession.status)}
                </p>
              </div>
              <span className="p-chip p-chip--info">
                <span className="d" />
                {t("analysis.chipHistory")}
              </span>
            </div>

            <div className="p-preview-banner">
              <span className="ic">i</span>
              <span className="tx">
                <strong>{t("analysis.historyBannerTitle")}</strong> — {t("analysis.historyBannerBody")}
              </span>
            </div>

            <div className="p-history-metrics">
              <SummaryMetric label={t("analysis.metricStarted")} value={formatSessionTime(historySession.started_at)} />
              <SummaryMetric label={t("analysis.metricEnded")} value={formatSessionTime(historySession.ended_at)} />
              <SummaryMetric label={t("analysis.metricTokens")} value={compactNumber(historySession.total_tokens)} />
              <SummaryMetric label={t("analysis.metricManualStops")} value={String(historySession.manual_stops_count)} />
            </div>

            <div className="p-analysis__grid">
              <div className="p-panel">
                <h4>{t("analysis.availableNow")}</h4>
                <p>{t("analysis.availableNowBody")}</p>
              </div>
              <div className="p-panel">
                <h4>{t("analysis.deferred")}</h4>
                <p>{t("analysis.deferredBody")}</p>
              </div>
            </div>

            <div className="p-details">
              <button
                className="p-disclosure"
                aria-expanded={showDetails}
                onClick={() => setShowDetails(!showDetails)}
              >
                <span style={{ transform: showDetails ? "rotate(180deg)" : "none", transition: "transform .2s" }}>
                  ⌄
                </span>{" "}
                {t("analysis.sessionDetails")}
              </button>
              {showDetails && (
                <div className="p-details__readout">
                  session_id: {historySession.id}
                  <br />
                  lesson_id: {historySession.lesson_id ?? "none"}
                  <br />
                  status: {historySession.status}
                  <br />
                  started_at: {historySession.started_at}
                  <br />
                  ended_at: {historySession.ended_at ?? "not recorded"}
                  <br />
                  total_tokens: {historySession.total_tokens}
                  <br />
                  manual_stops_count: {historySession.manual_stops_count}
                </div>
              )}
            </div>

            <div className="p-analysis__actions">
              <button className="btn btn--primary" onClick={onAgain}>
                {t("analysis.practiceAgain")}
              </button>
              <button className="btn btn--ghost" onClick={onHistory}>
                {t("analysis.pastSessions")}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const result = grading;
  if (!result) return null;
  const preview = result.is_dev_preview;

  return (
    <div className="p-view p-main">
      <div className="p-wrap">
        <div className="p-analysis">
          <div className="p-analysis__head">
            <div>
              <h2>{historySession ? t("analysis.titleSaved") : t("analysis.titleYours")}</h2>
              <p className="p-analysis__cap">
                {historySession
                  ? `${formatSessionTime(historySession.started_at)} · graded at ${formatSessionTime(result.graded_at)}`
                  : `Graded at ${formatSessionTime(result.graded_at)}`}
              </p>
            </div>
            {preview ? (
              <span className="p-chip p-chip--clay">
                <span className="d" />
                {t("analysis.chipPreview")}
              </span>
            ) : (
              <span className="p-chip p-chip--ok">
                <span className="d" />
                {t("analysis.chipGraded")}
              </span>
            )}
          </div>

          <HistorySummaryBanner session={historySession} />

          {preview && (
            <div className="p-preview-banner">
              <span className="ic">◍</span>
              <span className="tx">
                <strong>{t("analysis.previewTitle")}</strong> — {t("analysis.previewBody")}
              </span>
            </div>
          )}

          <div className="p-scores">
            <ScoreCard k={t("analysis.scoreOverall")} v={result.overall_score} overall />
            <ScoreCard k={t("analysis.scoreFluency")} v={result.fluency_score} />
            <ScoreCard k={t("analysis.scoreGrammar")} v={result.grammar_score} />
            <ScoreCard k={t("analysis.scoreVocab")} v={result.vocab_score} />
            {result.pronunciation_score != null && (
              <ScoreCard k={t("analysis.scorePronunciation")} v={result.pronunciation_score} />
            )}
          </div>

          <div className="p-analysis__grid">
            <div className="p-panel">
              <h4>{t("analysis.coachSummary")}</h4>
              <p>{result.ai_summary_feedback || t("analysis.noSummary")}</p>
            </div>
            <div className="p-panel">
              <h4>{t("analysis.corrections")}</h4>
              {result.detailed_corrections.length === 0 ? (
                <p>{t("analysis.noCorrections")}</p>
              ) : (
                result.detailed_corrections.map((item, i) => (
                  <div className="p-correction" key={i}>
                    {correctionText(item)}
                  </div>
                ))
              )}
            </div>
          </div>

          {result.skill_feedback.length > 0 && (
            <div className="p-panel p-skill-feedback">
              <h4>{t("analysis.skillFeedback")}</h4>
              {result.skill_feedback.map((item, i) => (
                <div className="p-skill-feedback__item" key={i}>
                  <div>
                    <strong>{skillLabel(item)}</strong>
                    {typeof item.summary === "string" && <p>{item.summary}</p>}
                    {typeof item.suggestion === "string" && <p className="p-note">{item.suggestion}</p>}
                  </div>
                  {skillScore(item) && <span>{skillScore(item)}</span>}
                </div>
              ))}
            </div>
          )}

          <div className="p-details">
            <button
              className="p-disclosure"
              aria-expanded={showDetails}
              onClick={() => setShowDetails(!showDetails)}
            >
              <span style={{ transform: showDetails ? "rotate(180deg)" : "none", transition: "transform .2s" }}>
                ⌄
              </span>{" "}
              {t("analysis.sessionDetails")}
            </button>
            {showDetails && (
              <div className="p-details__readout">
                session_id: {result.session_id}
                <br />
                provider: {result.provider ?? "unknown"}
                <br />
                grader_version: {result.grader_version ?? "unknown"}
                <br />
                score_schema_version: {result.score_schema_version}
                <br />
                is_dev_preview: {String(result.is_dev_preview)}
                <br />
                input_quality:
                <br />
                <pre>{safeJson(result.input_quality)}</pre>
              </div>
            )}
          </div>

          <div className="p-analysis__actions">
            <button className="btn btn--primary" onClick={onAgain}>
              Practice again
            </button>
            <button className="btn btn--ghost" onClick={onHistory}>
              Past sessions
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
