import { useState } from "react";
import type { SessionGradingResult, SessionGradingStatus } from "../../lib/gradingApi";
import type { SessionHistoryItem } from "../../lib/sessionApi";

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

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-history-metric">
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

function HistorySummaryBanner({ session }: { session?: SessionHistoryItem | null }) {
  if (!session) return null;
  return (
    <div className="p-history-summary">
      <div>
        <strong>Selected past session</strong>
        <p>
          {formatSessionTime(session.started_at)} · {formatStatus(session.status)}
        </p>
      </div>
      <div className="p-history-metrics p-history-metrics--mini">
        <SummaryMetric label="Ended" value={formatSessionTime(session.ended_at)} />
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
  const [showDetails, setShowDetails] = useState(false);

  if (status === "loading") {
    return (
      <div className="p-view p-main">
        <div className="p-wrap">
          <div className="p-analysis">
            <div className="p-analysis__head">
              <h2>{historySession ? "Saved session analysis" : "Your session analysis"}</h2>
              <span className="p-chip p-chip--busy">
                <span className="d" />
                Loading grading…
              </span>
            </div>
            <HistorySummaryBanner session={historySession} />
            <p style={{ fontSize: "var(--t-sm)", color: "var(--ink-3)", margin: "0 0 14px" }}>
              This usually takes a few seconds.
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
    const label = gradingStatus?.status === "processing" ? "Grading is running" : "Grading pending";
    return (
      <div className="p-view p-main">
        <div className="p-wrap p-center">
          <div className="p-analysis">
            <HistorySummaryBanner session={historySession} />
            <div className="p-panel p-evidence">
              <div className="p-spinner p-spinner--sm" style={{ margin: "0 auto 14px" }} />
              <h3>{label}</h3>
              <p>
                This session has ended and LUVE is waiting for the grading worker to finish. No score is
                shown until the real grading result is available.
              </p>
              {gradingStatus?.student_word_count != null && (
                <p className="p-note">Detected student words: {gradingStatus.student_word_count}</p>
              )}
              <div className="p-analysis__actions" style={{ justifyContent: "center" }}>
                {onRefreshGrading && (
                  <button className="btn btn--primary" onClick={onRefreshGrading}>
                    Check again
                  </button>
                )}
                <button className="btn btn--ghost" onClick={onHistory}>
                  Past sessions
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
              <h3>Not enough for full grading yet</h3>
              <p>
                We caught some speech, but not enough reliable English for a full score. Short phrases are
                still useful practice; try one longer answer so LUVE can give real feedback.
              </p>
              {gradingStatus?.student_word_count != null && (
                <p className="p-note">Detected student words: {gradingStatus.student_word_count}</p>
              )}
              {reason && <p className="p-note">Reason: {reason}</p>}
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                <button className="btn btn--primary" onClick={onAgain}>
                  Try one longer answer
                </button>
                <button className="btn btn--ghost" onClick={onHistory}>
                  Past sessions
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
              <h3>{status === "failed" ? "Grading failed" : "Grading unavailable"}</h3>
              <p>{gradingError || "LUVE couldn't load a grading result for this session yet."}</p>
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                {onRefreshGrading && (
                  <button className="btn btn--primary" onClick={onRefreshGrading}>
                    Retry
                  </button>
                )}
                <button className="btn btn--ghost" onClick={onAgain}>
                  Practice again
                </button>
                <button className="btn btn--ghost" onClick={onHistory}>
                  Past sessions
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
                <h2>Session summary</h2>
                <p className="p-analysis__cap">
                  {formatSessionTime(historySession.started_at)} · {formatStatus(historySession.status)}
                </p>
              </div>
              <span className="p-chip p-chip--info">
                <span className="d" />
                History
              </span>
            </div>

            <div className="p-preview-banner">
              <span className="ic">i</span>
              <span className="tx">
                <strong>Checking saved-session grading</strong> — this view starts from the real saved
                session summary, then loads any real grading status or result for the selected session.
                Transcript replay is still deferred.
              </span>
            </div>

            <div className="p-history-metrics">
              <SummaryMetric label="Started" value={formatSessionTime(historySession.started_at)} />
              <SummaryMetric label="Ended" value={formatSessionTime(historySession.ended_at)} />
            </div>

            <div className="p-analysis__grid">
              <div className="p-panel">
                <h4>Available now</h4>
                <p>
                  LUVE can show the saved session summary now and will load real grading status or result
                  from the authenticated grading endpoint when it is available.
                </p>
              </div>
              <div className="p-panel">
                <h4>Deferred</h4>
                <p>
                  Transcript replay is still deferred because the history list intentionally stays lean.
                </p>
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
                Session details
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

  const result = grading;
  if (!result) return null;
  const preview = result.is_dev_preview;

  return (
    <div className="p-view p-main">
      <div className="p-wrap">
        <div className="p-analysis">
          <div className="p-analysis__head">
            <div>
              <h2>{historySession ? "Saved session analysis" : "Your session analysis"}</h2>
              <p className="p-analysis__cap">
                {historySession
                  ? `${formatSessionTime(historySession.started_at)} · graded at ${formatSessionTime(result.graded_at)}`
                  : `Graded at ${formatSessionTime(result.graded_at)}`}
              </p>
            </div>
            {preview ? (
              <span className="p-chip p-chip--clay">
                <span className="d" />
                Preview
              </span>
            ) : (
              <span className="p-chip p-chip--ok">
                <span className="d" />
                Graded
              </span>
            )}
          </div>

          <HistorySummaryBanner session={historySession} />

          {preview && (
            <div className="p-preview-banner">
              <span className="ic">◍</span>
              <span className="tx">
                <strong>Preview feedback</strong> — automatically generated for the demo, not final
                pedagogical grading. This warning comes from the grading API.
              </span>
            </div>
          )}

          <div className="p-scores">
            <ScoreCard k="Overall" v={result.overall_score} overall />
            <ScoreCard k="Fluency" v={result.fluency_score} />
            <ScoreCard k="Grammar" v={result.grammar_score} />
            <ScoreCard k="Vocabulary" v={result.vocab_score} />
            {result.pronunciation_score != null && (
              <ScoreCard k="Pronunciation" v={result.pronunciation_score} />
            )}
          </div>

          <div className="p-analysis__grid">
            <div className="p-panel">
              <h4>Coach's summary</h4>
              <p>{result.ai_summary_feedback || "The grader returned no written summary."}</p>
            </div>
            <div className="p-panel">
              <h4>Corrections</h4>
              {result.detailed_corrections.length === 0 ? (
                <p>No specific corrections were returned.</p>
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
              <h4>Skill feedback</h4>
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
              Session details
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
