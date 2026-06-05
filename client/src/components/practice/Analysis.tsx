import { useState } from "react";
import type { SessionResult } from "../../lib/mock";

type Status = "loading" | "ready" | "insufficient";

interface AnalysisProps {
  status: Status;
  session: SessionResult | null;
  onAgain: () => void;
}

function ScoreCard({ k, v, overall }: { k: string; v: number; overall?: boolean }) {
  return (
    <div className={"p-score" + (overall ? " overall" : "")}>
      <div className="p-score__k">{k}</div>
      <div className="p-score__v">{v}</div>
      <div className="p-score__o">/ 10</div>
    </div>
  );
}

/** Session analysis — loading (skeletons), insufficient-evidence, or graded.
 *  All data is mock (lib/mock). Session History is deferred (no GET /sessions),
 *  so only "Practice again" is offered here. */
export function Analysis({ status, session, onAgain }: AnalysisProps) {
  const [showDetails, setShowDetails] = useState(false);

  if (status === "loading") {
    return (
      <div className="p-view p-main">
        <div className="p-wrap">
          <div className="p-analysis">
            <div className="p-analysis__head">
              <h2>Your session analysis</h2>
              <span className="p-chip p-chip--busy">
                <span className="d" />
                Grading your session…
              </span>
            </div>
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

  if (status === "insufficient") {
    return (
      <div className="p-view p-main">
        <div className="p-wrap p-center">
          <div className="p-analysis">
            <div className="p-panel p-evidence">
              <div className="em">🌱</div>
              <h3>Not quite enough to grade yet</h3>
              <p>
                We didn't catch enough speech this time. A longer chat — even two or three minutes —
                gives the coach plenty to work with.
              </p>
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                <button className="btn btn--primary" onClick={onAgain}>
                  Try a longer session
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const s = session;
  if (!s) return null;
  const preview = s.mode === "preview";

  return (
    <div className="p-view p-main">
      <div className="p-wrap">
        <div className="p-analysis">
          <div className="p-analysis__head">
            <div>
              <h2>Your session analysis</h2>
              <p className="p-analysis__cap">
                {s.dateLabel} · {s.durationLabel} conversation · {s.words} words spoken
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

          {preview && (
            <div className="p-preview-banner">
              <span className="ic">◍</span>
              <span className="tx">
                <strong>Preview feedback</strong> — automatically generated for the demo, not final
                pedagogical grading.
              </span>
            </div>
          )}

          <div className="p-scores">
            <ScoreCard k="Overall" v={s.overall} overall />
            <ScoreCard k="Fluency" v={s.fluency} />
            <ScoreCard k="Grammar" v={s.grammar} />
            <ScoreCard k="Vocabulary" v={s.vocab} />
          </div>

          <div className="p-analysis__grid">
            <div className="p-panel">
              <h4>Coach's summary</h4>
              <p>{s.summary}</p>
            </div>
            <div className="p-panel">
              <h4>Corrections</h4>
              {s.corrections.map((c, i) => (
                <div className="p-correction" key={i}>
                  <del>{c.del}</del> → <ins>{c.ins}</ins>
                </div>
              ))}
              <div className="p-correction" style={{ color: "var(--brand-ink)", fontWeight: 600 }}>
                Pronunciation: {s.pronunciation}
              </div>
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
                session_id: {s.id}
                <br />
                provider: {preview ? "offline" : "groq"}
                <br />
                grader_version: {preview ? "fake_grader.v1" : "llm_grader.v3"}
                <br />
                is_dev_preview: {preview ? "true" : "false"}
                <br />
                input_quality: {"{ snr: good, speech_ratio: 0.71 }"}
              </div>
            )}
          </div>

          <div className="p-analysis__actions">
            <button className="btn btn--primary" onClick={onAgain}>
              Practice again
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
