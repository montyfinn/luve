import { useState } from "react";

/**
 * Collapsible developer/observability panel — STATIC PLACEHOLDERS ONLY.
 * Collapsed by default so it never competes with the learner happy path. Later
 * phases wire real values (base URLs, health probes, event log). Nothing here
 * reads or displays secrets.
 */
export function DiagnosticsPanel() {
  const [open, setOpen] = useState(false);

  return (
    <section className={`diagnostics ${open ? "diagnostics--open" : ""}`}>
      <button
        type="button"
        className="diagnostics__summary"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>Developer diagnostics</span>
        <span className="diagnostics__chev" aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="diagnostics__body">
          <div className="diagnostics__row">
            <span className="diagnostics__key">Core API</span>
            <span className="diagnostics__val mono">not connected</span>
          </div>
          <div className="diagnostics__row">
            <span className="diagnostics__key">Gateway</span>
            <span className="diagnostics__val mono">not connected</span>
          </div>
          <div className="diagnostics__row">
            <span className="diagnostics__key">Health</span>
            <span className="diagnostics__val mono">—</span>
          </div>
          <div className="diagnostics__log">
            <span className="diagnostics__key">Event log</span>
            <pre className="mono diagnostics__logbox">No events yet.</pre>
          </div>
          <p className="diagnostics__note">
            Placeholder panel. Real endpoints, health probes, and logs are wired in later phases.
          </p>
        </div>
      )}
    </section>
  );
}
