from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from src.evaluation_input_builder import build_evaluation_input
from src.fake_grader import fake_grade


def main() -> None:
    session_id = UUID("11111111-1111-4111-8111-111111111111")
    user_id = UUID("22222222-2222-4222-8222-222222222222")
    raw_backup_json = [
        {
            "type": "USER_TURN",
            "timestamp": "2026-05-15T00:00:00Z",
            "payload": {
                "text": "Hello, my name is Monty.",
                "word_timestamps": [
                    {"word": "Hello", "start_ms": 0, "end_ms": 350},
                    {"word": "Monty", "start_ms": 1200, "end_ms": 1700},
                ],
            },
        },
        {
            "type": "AI_TURN",
            "timestamp": "2026-05-15T00:00:02Z",
            "payload": {
                "text": "Nice to meet you, Monty.",
                "source": "local_fallback",
            },
        },
        {
            "type": "USER_TURN",
            "timestamp": "2026-05-15T00:00:04Z",
            "payload": {
                "text": "I want to practice speaking English today.",
                "audio": {"audio_ms": 2600},
            },
        },
        {"type": "assistant_audio_meta", "payload": {"chunk_index": 0}},
        {"type": "USER_TURN", "payload": {"text": "   "}},
    ]
    session_row = {
        "id": session_id,
        "user_id": user_id,
        "lesson_id": None,
        "raw_backup_json": raw_backup_json,
    }

    evaluation_input = build_evaluation_input(session_row)
    grading_result = fake_grade(evaluation_input)
    assert evaluation_input.raw_event_count == 5
    assert len(evaluation_input.turns) == 3
    assert evaluation_input.quality_signals["ignored_events_count"] == 2
    assert grading_result.session_id == evaluation_input.session_id
    assert 0 <= grading_result.overall_score <= 100
    print(
        json.dumps(
            {
                "evaluation_input": evaluation_input.model_dump(mode="json"),
                "grading_result": grading_result.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print("PASS grading-worker evaluation input smoke")


if __name__ == "__main__":
    main()
