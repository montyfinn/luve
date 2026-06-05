import { useEffect } from "react";
import type { DiagState, GradingMode, LogLine } from "../lib/mock";
import { CORE_API_URL, GATEWAY_URL } from "../lib/config";
import { CloseIcon } from "./icons";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  state: DiagState;
  set: (p: Partial<DiagState>) => void;
  log: LogLine[];
  sessionId: string | null;
}

const GRADING_MODES: GradingMode[] = ["real", "preview", "insufficient"];

/**
 * Developer diagnostics drawer (operator plane). Closed by default; opens from
 * the top-bar gear. All readouts are MOCK/static placeholders. The "Demo
 * controls" let a reviewer preview states (Google enabled/paused, grading
 * result) without any backend — values feed the mock UI only.
 */
export function DiagnosticsDrawer({ open, onClose, state, set, log, sessionId }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="p-scrim" onClick={onClose} />
      <aside className="p-drawer" role="dialog" aria-label="Developer diagnostics" aria-modal="true">
        <div className="p-drawer__head">
          <h3>Developer diagnostics</h3>
          <button className="p-iconbtn" onClick={onClose} aria-label="Close diagnostics">
            <CloseIcon size={16} />
          </button>
        </div>
        <div className="p-drawer__body">
          <div>
            <div className="p-dgroup__title">Health</div>
            <div className="p-readline">
              <span className="k">core_api /readyz</span>
              <span className="v" style={{ color: "var(--ok-ink)" }}>● mock</span>
            </div>
            <div className="p-readline">
              <span className="k">gateway /readyz</span>
              <span className="v" style={{ color: "var(--ok-ink)" }}>● mock</span>
            </div>
            <div className="p-readline">
              <span className="k">grading</span>
              <span className="v" style={{ color: "var(--ink-3)" }}>
                {state.gradingMode === "real" ? "progressing" : "inferred ok"}
              </span>
            </div>
          </div>

          <div>
            <div className="p-dgroup__title">Session</div>
            <div className="p-readline">
              <span className="k">session_id</span>
              <span className="v" style={{ color: sessionId ? "var(--ok-ink)" : "var(--ink-3)" }}>
                {sessionId ? sessionId.slice(0, 8) + "…" : "none"}
              </span>
            </div>
            <div className="p-readline">
              <span className="k">rtc</span>
              <span className="v" style={{ color: "var(--ink-3)" }}>not connected (deferred)</span>
            </div>
            <div className="p-readline">
              <span className="k">transcript</span>
              <span className="v" style={{ color: "var(--busy-ink)" }}>mock</span>
            </div>
            <div className="p-readline">
              <span className="k">grading</span>
              <span className="v" style={{ color: "var(--busy-ink)" }}>mock (deferred)</span>
            </div>
          </div>

          <div>
            <div className="p-dgroup__title">Provider &amp; environment</div>
            <div className="p-readline">
              <span className="k">grader</span>
              <span className="v" style={{ color: state.gradingMode === "real" ? "var(--ok-ink)" : "var(--busy-ink)" }}>
                {state.gradingMode === "real" ? "llm_grader.v3" : "fake_grader.v1"}
              </span>
            </div>
            <div className="p-readline">
              <span className="k">google_oauth</span>
              <span className="v" style={{ color: state.googleEnabled ? "var(--ok-ink)" : "var(--ink-3)" }}>
                {state.googleEnabled ? "enabled" : "disabled"}
              </span>
            </div>
          </div>

          <div>
            <div className="p-dgroup__title">Demo controls</div>
            <div className="p-toggle-row" style={{ borderRadius: "10px" }}>
              <div className="lbl">
                <b>Google sign-in</b>
                <span>Simulate enabled / paused.</span>
              </div>
              <button
                className={"p-switch" + (state.googleEnabled ? " on" : "")}
                aria-pressed={state.googleEnabled}
                aria-label="Simulate Google sign-in"
                onClick={() => set({ googleEnabled: !state.googleEnabled })}
              />
            </div>
            <div style={{ marginTop: "10px" }}>
              <span className="p-dlabel">Grading result</span>
              <div className="p-segwrap">
                {GRADING_MODES.map((m) => (
                  <button
                    key={m}
                    className={"p-seg" + (state.gradingMode === m ? " on" : "")}
                    onClick={() => set({ gradingMode: m })}
                  >
                    {m === "real" ? "Real LLM" : m === "preview" ? "Dev preview" : "Insufficient"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <div className="p-dgroup__title">Connection</div>
            <span className="p-dlabel">core-api URL</span>
            <input className="p-input p-input--mono" defaultValue={CORE_API_URL} readOnly />
            <span className="p-dlabel" style={{ marginTop: "10px" }}>gateway URL (used in the realtime phase)</span>
            <input className="p-input p-input--mono" defaultValue={GATEWAY_URL} readOnly />
            <span className="p-dlabel" style={{ marginTop: "10px" }}>Bearer token (escape hatch)</span>
            <input className="p-input p-input--mono" placeholder="paste token…" />
          </div>

          <div>
            <div className="p-dgroup__title">Event log</div>
            <div className="p-log">
              {log.length === 0 && <span className="t">— no events yet —</span>}
              {log.map((l, i) => (
                <div key={i}>
                  <span className="t">{l.t}</span> {l.m}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="p-drawer__foot">Demo build — not production-ready.</div>
      </aside>
    </>
  );
}
