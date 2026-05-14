from __future__ import annotations


HALLUCINATION_PATTERNS = (
    "spoken english conversation",
    "ai tutor",
    "learner and an ai",
    "english conversation between",
    "thank you for watching",
    "please read or speak",
)


def sanitize_transcript(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    if any(pattern in lowered for pattern in HALLUCINATION_PATTERNS):
        return ""

    if len(cleaned) < 2:
        return ""

    return _filter_repetitions(cleaned)


def _filter_repetitions(text: str) -> str:
    parts = text.split(". ")
    if len(parts) < 2:
        return text

    unique_parts: list[str] = []
    for part in parts:
        part = part.strip()
        if not unique_parts or part != unique_parts[-1]:
            unique_parts.append(part)
    return ". ".join(unique_parts)

