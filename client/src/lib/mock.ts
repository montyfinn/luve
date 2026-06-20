/**
 * Local mock data for the high-fidelity visual port. Everything here is static /
 * scripted — NO backend calls. Ported from the Claude Design prototype
 * (docs/design/luvedesign/proto-app.jsx + proto-live-analysis.jsx).
 *
 * The "API" strings in the event log and the scripted conversation beats are
 * presentational only; real auth/realtime/grading wiring lands in later phases.
 */

export type Phase =
  | "connecting"
  | "listening"
  | "speaking"
  | "stt"
  | "thinking"
  | "aispeaking";

export interface PhaseMeta {
  label: string;
  help: string;
  chip: [string, string]; // [variant, label]
  orb: string;
}

export const PHASE_META: Record<Phase, PhaseMeta> = {
  connecting: { label: "Connecting…", help: "Setting up your session", chip: ["info", "Connecting"], orb: "" },
  listening: { label: "Listening…", help: "Speak naturally — I'm listening", chip: ["ok", "Connected"], orb: "listening" },
  speaking: { label: "You're speaking", help: "Keep going — I'm following along", chip: ["ok", "Connected"], orb: "speaking" },
  stt: { label: "Got it…", help: "Finishing what you said", chip: ["busy", "Processing"], orb: "speaking" },
  thinking: { label: "Thinking…", help: "Your tutor is forming a reply", chip: ["busy", "Thinking"], orb: "thinking" },
  aispeaking: { label: "Your tutor is speaking", help: "Your tutor is replying — listen along", chip: ["ok", "Connected"], orb: "aispeaking" },
};

export const AI_LINES = [
  "That sounds like a wonderful trip. What was the most memorable meal you had there?",
  "Lovely — and would you say you're more of a beach person or a mountains person?",
  "Beautifully put. Tell me about a place you'd love to visit next.",
];

export const YOU_LINES = [
  "The best meal was a small place near the harbor — we ate fresh fish every night.",
  "I think I prefer the mountains, because the air feels so calm up there.",
];

export interface Beat {
  phase: Phase | "commit";
  ai?: number;
  you?: number;
  dur: number;
}

// Scripted live-conversation beats. 'commit' pushes the partial as a final turn.
export const BEATS: Beat[] = [
  { phase: "aispeaking", ai: 0, dur: 2600 },
  { phase: "listening", dur: 1400 },
  { phase: "speaking", you: 0, dur: 2800 },
  { phase: "stt", dur: 900 },
  { phase: "commit", you: 0, dur: 250 },
  { phase: "thinking", dur: 1700 },
  { phase: "aispeaking", ai: 1, dur: 2800 },
  { phase: "listening", dur: 1400 },
  { phase: "speaking", you: 1, dur: 2700 },
  { phase: "stt", dur: 900 },
  { phase: "commit", you: 1, dur: 250 },
  { phase: "thinking", dur: 1600 },
  { phase: "aispeaking", ai: 2, dur: 2800 },
  { phase: "listening", dur: 4000 },
];

export type GradingMode = "real" | "preview" | "insufficient";

export interface Correction {
  del: string;
  ins: string;
}

export interface SessionResult {
  id: string;
  mode: GradingMode;
  dateLabel: string;
  durationLabel: string;
  words: number;
  overall: number;
  fluency: number;
  grammar: number;
  vocab: number;
  pronunciation: string;
  summary: string;
  corrections: Correction[];
}

const CORRECTIONS: Correction[] = [
  { del: "we ate fresh fish every night", ins: "we ate fresh fish every night (natural!)" },
  { del: "the air feels so calm", ins: "the air feels so calm up there" },
  { del: "I prefer the mountains", ins: "I prefer the mountains because…" },
];

export function buildCurrentSession(mode: GradingMode): SessionResult {
  const preview = mode === "preview";
  return {
    id: "sess_" + Math.random().toString(36).slice(2, 8),
    mode,
    dateLabel: "Just now",
    durationLabel: "2:14",
    words: 86,
    overall: preview ? 7.2 : 7.8,
    fluency: preview ? 7.0 : 7.5,
    grammar: preview ? 7.5 : 8.1,
    vocab: preview ? 7.1 : 7.6,
    pronunciation: "clear, with a gentle natural rhythm.",
    summary:
      "A relaxed, natural conversation. Your fluency held up well across longer turns, and your vocabulary around travel was varied. The main thing to keep polishing is linking clauses smoothly — a couple of sentences trailed off where a connecting word would help.",
    corrections: CORRECTIONS,
  };
}

export interface DiagState {
  googleEnabled: boolean;
  gradingMode: GradingMode;
}

export interface LogLine {
  t: string;
  m: string;
}
