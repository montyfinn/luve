from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np
from av.audio.resampler import AudioResampler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import settings
from src.media.audio_frame_utils import extend_pcm16le_from_frames
from src.media.stt_postprocess import sanitize_transcript
from src.media.stt_worker import WhisperInference


TARGET_SAMPLE_RATE = 16000
TARGET_LAYOUT = "mono"
TARGET_FORMAT = "s16"


@dataclass(frozen=True)
class STTCase:
    case_id: str
    audio_path: Path
    expected_text: str
    notes: str = ""


def normalize_text(text: str) -> str:
    collapsed = re.sub(r"[^a-z0-9']+", " ", text.lower()).strip()
    return re.sub(r"\s+", " ", collapsed)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    dp = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    for i in range(len(ref_words) + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j

    for i, ref_word in enumerate(ref_words, start=1):
        for j, hyp_word in enumerate(hyp_words, start=1):
            cost = 0 if ref_word == hyp_word else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )

    return dp[-1][-1] / len(ref_words)


def load_cases(manifest_path: Path) -> list[STTCase]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[STTCase] = []
    for item in payload.get("cases", []):
        audio_path = (manifest_path.parent / item["audio_path"]).resolve()
        cases.append(
            STTCase(
                case_id=item["id"],
                audio_path=audio_path,
                expected_text=item["expected_text"],
                notes=item.get("notes", ""),
            )
        )
    return cases


def decode_audio_to_pcm16(audio_path: Path) -> bytes:
    output = bytearray()
    resampler = AudioResampler(
        format=TARGET_FORMAT,
        layout=TARGET_LAYOUT,
        rate=TARGET_SAMPLE_RATE,
    )
    with av.open(str(audio_path), mode="r") as container:
        for frame in container.decode(audio=0):
            converted = resampler.resample(frame)
            frames = converted if isinstance(converted, list) else [converted]
            extend_pcm16le_from_frames(output, frames)

        flushed = resampler.resample(None)
        flush_frames = flushed if isinstance(flushed, list) else [flushed]
        extend_pcm16le_from_frames(output, flush_frames)
    return bytes(output)


async def evaluate_case(case: STTCase) -> dict[str, object]:
    audio_bytes = decode_audio_to_pcm16(case.audio_path)
    stt = await WhisperInference.get_instance(
        model_size=settings.stt_model_size,
        preferred_device="cuda",
        preferred_compute_type="float16",
        beam_size=settings.stt_beam_size,
    )
    analysis = await stt.transcribe_audio_bytes(
        audio_bytes,
        initial_prompt=settings.stt_initial_prompt,
        beam_size=settings.stt_final_beam_size,
        word_timestamps=False,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    cleaned_text = sanitize_transcript(analysis.raw_text)
    wer = word_error_rate(case.expected_text, cleaned_text)
    return {
        "id": case.case_id,
        "audio_path": str(case.audio_path),
        "expected_text": case.expected_text,
        "raw_text": analysis.raw_text,
        "cleaned_text": cleaned_text,
        "normalized_expected": normalize_text(case.expected_text),
        "normalized_cleaned": normalize_text(cleaned_text),
        "wer": round(wer, 4),
        "exact_match": normalize_text(case.expected_text) == normalize_text(cleaned_text),
        "notes": case.notes,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate final STT accuracy on fixed local audio cases."
    )
    parser.add_argument(
        "--manifest",
        default="testdata/stt_cases.json",
        help="Path to JSON manifest containing fixed STT evaluation cases.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    cases = load_cases(manifest_path)
    if not cases:
        raise SystemExit(
            "No STT cases found. Add fixed audio samples to the manifest before running evaluation."
        )

    results: list[dict[str, object]] = []
    for case in cases:
        if not case.audio_path.exists():
            raise SystemExit(f"Missing audio file for case '{case.case_id}': {case.audio_path}")
        results.append(await evaluate_case(case))

    output = {
        "model_size": settings.stt_model_size,
        "final_beam_size": settings.stt_final_beam_size,
        "cases": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
