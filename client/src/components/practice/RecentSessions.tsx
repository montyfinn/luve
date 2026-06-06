import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../lib/authApi";
import { listSessions, type SessionHistoryItem } from "../../lib/sessionApi";
import { CatCompanion } from "../CatCompanion";
import { CloseIcon } from "../icons";

type LoadState = "loading" | "empty" | "error" | "loaded";

interface RecentSessionsProps {
  open: boolean;
  currentId?: string | null;
  selectedId?: string | null;
  onClose: () => void;
  onSelect: (session: SessionHistoryItem) => void;
  onLog?: (message: string) => void;
}

const HISTORY_LIMIT = 10;

function formatSessionTime(value: string): string {
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

function sessionSubtitle(session: SessionHistoryItem): string {
  const parts = [formatStatus(session.status)];
  if (session.ended_at) parts.push(`Ended ${formatSessionTime(session.ended_at)}`);
  return parts.join(" · ");
}

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ),
  );
}

export function RecentSessions({ open, currentId, selectedId, onClose, onSelect, onLog }: RecentSessionsProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [items, setItems] = useState<SessionHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const result = await listSessions({ limit: HISTORY_LIMIT, offset: 0 });
      setItems(result.items);
      setTotal(result.total);
      setState(result.items.length === 0 ? "empty" : "loaded");
      onLog?.(
        `GET /api/v1/sessions?limit=${HISTORY_LIMIT}&offset=0 -> 200 (${result.items.length}/${result.total})`,
      );
    } catch (e) {
      const message = e instanceof ApiError || e instanceof Error ? e.message : "Couldn't load session history.";
      setItems([]);
      setTotal(0);
      setError(message);
      setState("error");
      onLog?.(`GET /api/v1/sessions?limit=${HISTORY_LIMIT}&offset=0 -> failed`);
    }
  }, [onLog]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [load, open]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusTimer = window.setTimeout(() => closeRef.current?.focus(), 0);

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      const targets = focusableElements(panelRef.current);
      if (targets.length === 0) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  const countLabel =
    state === "loaded"
      ? `${items.length} of ${total} practice ${total === 1 ? "session" : "sessions"}`
      : state === "empty"
        ? "No practice sessions yet"
        : state === "error"
          ? "History unavailable"
          : "Loading practice sessions";

  return (
    <>
      <div className="p-history-scrim" onClick={onClose} />
      <div ref={panelRef} className="p-history-panel" role="dialog" aria-modal="true" aria-label="Your past sessions">
        <div className="p-history-head">
          <div>
            <h3>Your sessions</h3>
            <div className="sub">{countLabel}</div>
          </div>
          <button ref={closeRef} className="p-iconbtn" type="button" onClick={onClose} aria-label="Close history">
            <CloseIcon size={16} />
          </button>
        </div>

        {state === "loading" && (
          <div className="p-history-list" aria-label="Loading session history">
            <div className="p-history-skel" />
            <div className="p-history-skel" />
            <div className="p-history-skel" />
          </div>
        )}

        {state === "empty" && (
          <div className="p-history-state">
            <CatCompanion variant="sleepy" size={64} />
            <strong>No sessions yet.</strong>
            <span>Start a practice session and it will appear here when the backend stores it.</span>
          </div>
        )}

        {state === "error" && (
          <div className="p-history-state p-history-state--err" role="alert">
            <strong>{error}</strong>
            <button className="p-linkbtn" type="button" onClick={() => void load()}>
              Retry
            </button>
          </div>
        )}

        {state === "loaded" && (
          <div className="p-history-list">
            {items.map((session) => {
              const selected = session.id === selectedId;
              const current = session.id === currentId;
              return (
                <button
                  className={`p-session-row${selected ? " is-selected" : ""}`}
                  key={session.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelect(session)}
                >
                  <span className="p-sr-score none" aria-hidden="true">
                    -
                  </span>
                  <span className="sr-main">
                    <span className="sr-date">
                      {formatSessionTime(session.started_at)}
                      {current && <span className="p-cur-tag">Current</span>}
                    </span>
                    <span className="sr-sub">{sessionSubtitle(session)}</span>
                  </span>
                  <svg
                    className="p-sr-chev"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              );
            })}
          </div>
        )}

        <div className="p-history-foot">
          Select a session to open its saved summary and grading status. Transcript replay is coming later.
        </div>
      </div>
    </>
  );
}
