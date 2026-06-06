import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../lib/authApi";
import { listSessions, type SessionHistoryItem } from "../../lib/sessionApi";

type LoadState = "loading" | "empty" | "error" | "loaded";

interface RecentSessionsProps {
  onLog?: (message: string) => void;
}

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

function statusChipClass(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (["ready", "completed", "ended"].includes(normalized)) return "p-chip p-chip--ok";
  if (["waiting", "processing", "running", "active"].includes(normalized)) return "p-chip p-chip--busy";
  if (["failed", "error"].includes(normalized)) return "p-chip p-chip--err";
  return "p-chip p-chip--info";
}

function compactNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { notation: value >= 1000 ? "compact" : "standard" }).format(value);
}

export function RecentSessions({ onLog }: RecentSessionsProps) {
  const [state, setState] = useState<LoadState>("loading");
  const [items, setItems] = useState<SessionHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    setError(null);
    setSelectedId(null);
    try {
      const result = await listSessions({ limit: 5, offset: 0 });
      setItems(result.items);
      setTotal(result.total);
      setState(result.items.length === 0 ? "empty" : "loaded");
      onLog?.(`GET /api/v1/sessions?limit=5&offset=0 -> 200 (${result.items.length}/${result.total})`);
    } catch (e) {
      const message = e instanceof ApiError || e instanceof Error ? e.message : "Couldn't load recent sessions.";
      setItems([]);
      setTotal(0);
      setError(message);
      setState("error");
      onLog?.("GET /api/v1/sessions?limit=5&offset=0 -> failed");
    }
  }, [onLog]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="p-recent" aria-label="Recent sessions">
      <div className="p-recent__head">
        <div>
          <h3>Recent sessions</h3>
          <p>{state === "loaded" && total > items.length ? `${items.length} of ${total}` : "Latest practice"}</p>
        </div>
        {state !== "loading" && (
          <button className="p-linkbtn" type="button" onClick={() => void load()}>
            Refresh
          </button>
        )}
      </div>

      {state === "loading" && (
        <div className="p-recent__loading" aria-label="Loading recent sessions">
          <div className="p-skel p-skel--line" />
          <div className="p-skel p-skel--line" />
          <div className="p-skel p-skel--line" />
        </div>
      )}

      {state === "empty" && <div className="p-recent__state">No recent sessions yet.</div>}

      {state === "error" && (
        <div className="p-recent__state p-recent__state--err" role="alert">
          <span>{error}</span>
          <button className="p-linkbtn" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      )}

      {state === "loaded" && (
        <>
          <div className="p-recent__list">
            {items.map((session) => (
              <button
                key={session.id}
                className="p-recent__item"
                type="button"
                onClick={() => setSelectedId(session.id)}
              >
                <span className="p-recent__top">
                  <span className="p-recent__when">{formatSessionTime(session.started_at)}</span>
                  <span className={statusChipClass(session.status)}>
                    <span className="d" />
                    {formatStatus(session.status)}
                  </span>
                </span>
                <span className="p-recent__meta">
                  <span>{compactNumber(session.total_tokens)} tokens</span>
                  <span>{session.manual_stops_count} stops</span>
                  {session.ended_at && <span>Ended {formatSessionTime(session.ended_at)}</span>}
                </span>
              </button>
            ))}
          </div>
          {selectedId && (
            <div className="p-recent__notice" role="status">
              Details coming later for {selectedId.slice(0, 8)}...
            </div>
          )}
        </>
      )}
    </section>
  );
}
