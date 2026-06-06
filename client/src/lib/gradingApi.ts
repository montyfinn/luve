import { CORE_API_URL } from "./config";
import { ApiError } from "./authApi";
import { loadToken } from "./session";

export type SessionGradingStatusValue =
  | "graded"
  | "processing"
  | "pending"
  | "insufficient_evidence"
  | "failed";

export interface SessionGradingStatus {
  session_id: string;
  status: SessionGradingStatusValue;
  student_word_count: number | null;
  reason: string | null;
  error_code: string | null;
}

export interface SessionGradingResult {
  session_id: string;
  status: "graded";
  provider: string | null;
  grader_version: string | null;
  score_schema_version: string;
  overall_score: number;
  fluency_score: number;
  grammar_score: number;
  vocab_score: number;
  pronunciation_score: number | null;
  detailed_corrections: Array<Record<string, unknown>>;
  skill_feedback: Array<Record<string, unknown>>;
  input_quality: Record<string, unknown>;
  ai_summary_feedback: string;
  error_code: string | null;
  error_message: string | null;
  graded_at: string;
  is_dev_preview: boolean;
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return fallback;
}

function authHeaders(): HeadersInit {
  const token = loadToken();
  if (!token) {
    throw new ApiError("Please sign in again to load grading.", 401);
  }
  return { Authorization: `Bearer ${token}` };
}

async function getJson(path: string, fallback: string): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(CORE_API_URL + path, { headers: authHeaders() });
  } catch {
    throw new ApiError("Couldn't reach the server. Is the API running?", 0);
  }

  const payload = await res.json().catch(() => null);
  if (res.status === 401) {
    throw new ApiError("Your session expired — please sign in again.", 401);
  }
  if (!res.ok) {
    throw new ApiError(formatDetail((payload as { detail?: unknown })?.detail, fallback), res.status);
  }
  return payload;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : [];
}

function parseStatus(payload: unknown): SessionGradingStatus {
  const body = payload as Partial<SessionGradingStatus> | null;
  const status = body?.status;
  if (
    !body ||
    typeof body.session_id !== "string" ||
    !(
      status === "graded" ||
      status === "processing" ||
      status === "pending" ||
      status === "insufficient_evidence" ||
      status === "failed"
    )
  ) {
    throw new ApiError("Grading status response was malformed.", 0);
  }

  return {
    session_id: body.session_id,
    status,
    student_word_count: nullableNumber(body.student_word_count),
    reason: nullableString(body.reason),
    error_code: nullableString(body.error_code),
  };
}

function parseResult(payload: unknown): SessionGradingResult {
  const body = payload as Partial<SessionGradingResult> | null;
  if (
    !body ||
    typeof body.session_id !== "string" ||
    body.status !== "graded" ||
    typeof body.overall_score !== "number" ||
    typeof body.fluency_score !== "number" ||
    typeof body.grammar_score !== "number" ||
    typeof body.vocab_score !== "number" ||
    typeof body.ai_summary_feedback !== "string" ||
    typeof body.graded_at !== "string"
  ) {
    throw new ApiError("Grading result response was malformed.", 0);
  }

  return {
    session_id: body.session_id,
    status: "graded",
    provider: nullableString(body.provider),
    grader_version: nullableString(body.grader_version),
    score_schema_version: body.score_schema_version || "grading.v1",
    overall_score: body.overall_score,
    fluency_score: body.fluency_score,
    grammar_score: body.grammar_score,
    vocab_score: body.vocab_score,
    pronunciation_score: nullableNumber(body.pronunciation_score),
    detailed_corrections: asRecordArray(body.detailed_corrections),
    skill_feedback: asRecordArray(body.skill_feedback),
    input_quality: asRecord(body.input_quality),
    ai_summary_feedback: body.ai_summary_feedback,
    error_code: nullableString(body.error_code),
    error_message: nullableString(body.error_message),
    graded_at: body.graded_at,
    is_dev_preview: body.is_dev_preview === true,
  };
}

export async function getSessionGradingStatus(sessionId: string): Promise<SessionGradingStatus> {
  const payload = await getJson(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/grading/status`,
    "Couldn't load grading status.",
  );
  return parseStatus(payload);
}

export async function getSessionGradingResult(sessionId: string): Promise<SessionGradingResult> {
  const payload = await getJson(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/grading`,
    "Couldn't load grading result.",
  );
  return parseResult(payload);
}
