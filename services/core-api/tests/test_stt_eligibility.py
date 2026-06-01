from __future__ import annotations

import asyncio

import pytest

from src.schemas.ai_logic import STTAnalysis, WordPoint
from src.ten_ext.luve_extension import LUVEExtension


class MockLUVEExtension(LUVEExtension):
    def __init__(self) -> None:
        self._stt_final_min_speech_ms = 180
        self._stt_second_pass_verification_enabled = False
        self._stt_worker = None


@pytest.fixture()
def extension() -> MockLUVEExtension:
    return MockLUVEExtension()


def _make_analysis(
    text: str,
    *,
    no_speech_prob: float | None,
    avg_logprob: float | None,
    compression_ratio: float = 1.0,
    word_confidences: list[float] | None = None,
) -> STTAnalysis:
    tokens = text.split()
    confidences = word_confidences or []
    all_words = [
        WordPoint(
            word=token,
            confidence=confidences[index] if index < len(confidences) else 0.95,
            start_ms=index * 100,
            end_ms=(index + 1) * 100,
        )
        for index, token in enumerate(tokens)
    ]
    return STTAnalysis(
        raw_text=text,
        all_words=all_words,
        no_speech_prob=no_speech_prob,
        avg_logprob=avg_logprob,
        compression_ratio=compression_ratio,
    )


class FakeSTTWorker:
    def __init__(self, result: STTAnalysis) -> None:
        self.result = result
        self.calls = 0

    async def transcribe_audio_bytes(self, *_args: object, **_kwargs: object) -> STTAnalysis:
        self.calls += 1
        return self.result


def test_stt_language_mode_maps_to_transcription_language() -> None:
    assert LUVEExtension._stt_transcription_language("forced_en") == "en"
    assert LUVEExtension._stt_transcription_language("auto") is None
    assert LUVEExtension._stt_transcription_language("auto_en_vi") is None
    assert LUVEExtension._stt_transcription_language("invalid") == "en"


def test_auto_language_mode_derives_multilingual_model() -> None:
    assert LUVEExtension._select_stt_model_size("small.en", "forced_en") == "small.en"
    assert LUVEExtension._select_stt_model_size("small.en", "auto") == "small"
    assert LUVEExtension._select_stt_model_size("base.en", "auto_en_vi") == "base"
    assert LUVEExtension._select_stt_model_size("small", "auto") == "small"


def test_is_english_like_utterance(extension: MockLUVEExtension) -> None:
    assert extension._english_token_count("I go school yesterday") == 4
    assert extension._english_token_count("") == 0

    assert extension._has_learner_english_evidence("I go school yesterday") is True
    assert extension._has_learner_english_evidence("she don't like coffee") is True
    assert extension._has_learner_english_evidence("yes please") is True
    assert extension._has_learner_english_evidence("hôm nay tôi đi học") is False
    assert extension._has_learner_english_evidence("") is False
    assert extension._has_learner_english_evidence("yes") is False


def test_is_plausible_short_english_utterance(extension: MockLUVEExtension) -> None:
    conf_ok = {"word_count": 1, "low_confidence_word_ratio": 0.10}
    conf_poor = {"word_count": 1, "low_confidence_word_ratio": 0.50}

    analysis_yes = _make_analysis(
        "yes",
        no_speech_prob=0.05,
        avg_logprob=-0.25,
    )
    assert (
        extension._is_plausible_short_english_utterance(
            analysis_yes,
            {"speech_ms": 400},
            conf_ok,
        )
        is True
    )

    analysis_poor_ns = _make_analysis(
        "yes",
        no_speech_prob=0.80,
        avg_logprob=-0.25,
    )
    assert (
        extension._is_plausible_short_english_utterance(
            analysis_poor_ns,
            {"speech_ms": 400},
            conf_ok,
        )
        is False
    )

    assert (
        extension._is_plausible_short_english_utterance(
            analysis_yes,
            {"speech_ms": 200},
            conf_ok,
        )
        is False
    )

    analysis_poor_logprob = _make_analysis(
        "yes",
        no_speech_prob=0.05,
        avg_logprob=-0.82,
    )
    assert (
        extension._is_plausible_short_english_utterance(
            analysis_poor_logprob,
            {"speech_ms": 400},
            conf_ok,
        )
        is False
    )

    assert (
        extension._is_plausible_short_english_utterance(
            analysis_yes,
            {"speech_ms": 400},
            conf_poor,
        )
        is False
    )

    analysis_phrase = _make_analysis(
        "good morning",
        no_speech_prob=0.09,
        avg_logprob=-0.58,
        word_confidences=[0.92, 0.88],
    )
    assert (
        extension._is_plausible_short_english_utterance(
            analysis_phrase,
            {"speech_ms": 820},
            {"word_count": 2, "low_confidence_word_ratio": 0.0},
        )
        is True
    )

    analysis_bad_token = _make_analysis(
        "you",
        no_speech_prob=0.05,
        avg_logprob=-0.30,
    )
    assert (
        extension._is_plausible_short_english_utterance(
            analysis_bad_token,
            {"speech_ms": 420},
            conf_ok,
        )
        is False
    )


def test_confident_quality_examples(extension: MockLUVEExtension) -> None:
    cases = [
        (
            "hello",
            _make_analysis("hello", no_speech_prob=0.08, avg_logprob=-0.32),
            {"speech_ms": 700, "audio_ms": 900},
        ),
        (
            "hello guys",
            _make_analysis("hello guys", no_speech_prob=0.08, avg_logprob=-0.34),
            {"speech_ms": 900, "audio_ms": 1100},
        ),
        (
            "yes",
            _make_analysis("yes", no_speech_prob=0.05, avg_logprob=-0.25),
            {"speech_ms": 400, "audio_ms": 520},
        ),
        (
            "I go school yesterday",
            _make_analysis(
                "I go school yesterday",
                no_speech_prob=0.12,
                avg_logprob=-0.48,
            ),
            {"speech_ms": 1200, "audio_ms": 1500},
        ),
        (
            "She don't like coffee",
            _make_analysis(
                "She don't like coffee",
                no_speech_prob=0.11,
                avg_logprob=-0.44,
            ),
            {"speech_ms": 1250, "audio_ms": 1550},
        ),
    ]

    for text, analysis, audio_stats in cases:
        metadata = extension._stt_quality_assessment(
            analysis,
            audio_stats=audio_stats,
            inference_ms=88.4,
        )
        assert metadata["confidence"] == 1.0, text
        assert metadata["stt_quality"] == "confident", text
        assert metadata["uncertainty_reasons"] == [], text
        assert metadata["possible_hallucination"] is False, text
        assert metadata["possible_stt_autocorrection"] is False, text
        assert metadata["stt_confidence"]["confidence_score"] is None, text
        assert metadata["stt_confidence"]["avg_logprob"] == analysis.avg_logprob, text
        assert metadata["audio"] == audio_stats, text


def test_uncertain_quality_examples(extension: MockLUVEExtension) -> None:
    hello = extension._stt_quality_assessment(
        _make_analysis("hello", no_speech_prob=0.28, avg_logprob=-0.48),
        audio_stats={"speech_ms": 700, "audio_ms": 900},
        inference_ms=81.2,
    )
    assert hello["stt_quality"] == "uncertain"
    assert hello["uncertainty_reasons"] == ["high_no_speech_probability"]

    broken = extension._stt_quality_assessment(
        _make_analysis(
            "I very like this lesson",
            no_speech_prob=0.18,
            avg_logprob=-0.78,
            word_confidences=[0.92, 0.91, 0.93, 0.94, 0.90],
        ),
        audio_stats={"speech_ms": 1350, "audio_ms": 1700},
        inference_ms=92.0,
    )
    assert broken["stt_quality"] == "uncertain"
    assert broken["possible_stt_autocorrection"] is True
    assert broken["uncertainty_reasons"] == [
        "low_average_logprob",
        "possible_stt_autocorrection",
    ]

    low_conf = extension._stt_quality_assessment(
        _make_analysis(
            "I go school yesterday",
            no_speech_prob=0.10,
            avg_logprob=-0.50,
            word_confidences=[0.92, 0.41, 0.44, 0.93],
        ),
        audio_stats={"speech_ms": 1250, "audio_ms": 1500},
        inference_ms=90.6,
    )
    assert low_conf["stt_quality"] == "uncertain"
    assert low_conf["possible_stt_autocorrection"] is False
    assert low_conf["uncertainty_reasons"] == ["many_low_confidence_words"]
    assert low_conf["stt_confidence"]["low_confidence_word_count"] == 2
    assert low_conf["stt_confidence"]["word_count"] == 4


def test_short_wh_words_can_pass_when_plausible(extension: MockLUVEExtension) -> None:
    for text in (
        "hello",
        "what",
        "where",
        "who",
        "why",
        "how",
        "good morning",
        "thank you",
        "my name",
        "your name",
    ):
        analysis = _make_analysis(
            text,
            no_speech_prob=0.12,
            avg_logprob=-0.48,
        )
        assert (
            extension._stt_rejection_reason(
                analysis,
                is_final=True,
                audio_stats={"speech_ms": 420},
            )
            is None
        ), text

        metadata = extension._stt_quality_assessment(
            analysis,
            audio_stats={"speech_ms": 760, "audio_ms": 940},
            inference_ms=74.0,
        )
        assert metadata["stt_quality"] in {"confident", "uncertain"}, text
        assert metadata["confidence"] == 1.0, text
        assert "stt_confidence" in metadata, text


def test_short_wh_words_with_bad_metrics_are_suppressed(
    extension: MockLUVEExtension,
) -> None:
    bad_cases = (
        ("what", 0.72, -1.10, {"speech_ms": 420}),
        ("you", 0.90, -1.40, {"speech_ms": 400}),
        ("the", 0.84, -1.05, {"speech_ms": 410}),
        ("to", 0.82, -1.00, {"speech_ms": 430}),
        ("a", 0.86, -1.15, {"speech_ms": 360}),
    )
    for text, no_speech_prob, avg_logprob, audio_stats in bad_cases:
        analysis = _make_analysis(
            text,
            no_speech_prob=no_speech_prob,
            avg_logprob=avg_logprob,
        )
        reason = extension._stt_rejection_reason(
            analysis,
            is_final=True,
            audio_stats=audio_stats,
        )
        assert reason in {
            "high_no_speech_probability",
            "low_average_logprob",
            "too_few_words",
            "low_speech_duration",
            "mixed_non_english",
            "no_english_evidence",
        }, text
    assert (
        extension._stt_rejection_reason(
            _make_analysis("your name", no_speech_prob=0.72, avg_logprob=-1.10),
            is_final=True,
            audio_stats={"speech_ms": 420},
        )
        in {"low_speech_duration", "high_no_speech_probability", "low_average_logprob"}
    )


def test_incomplete_fragments_are_preserved_for_tutor_context(
    extension: MockLUVEExtension,
) -> None:
    for text in ("I want", "Can you", "What is", "Where is", "I need"):
        analysis = _make_analysis(
            text,
            no_speech_prob=0.08,
            avg_logprob=-0.30,
        )
        assert (
            extension._stt_rejection_reason(
                analysis,
                is_final=True,
                audio_stats={"speech_ms": 760},
            )
            is None
        ), text
        metadata = extension._stt_quality_assessment(
            analysis,
            audio_stats={"speech_ms": 760, "audio_ms": 920},
            inference_ms=70.0,
        )
        assert metadata["tutor_visible"] is True, text
        assert metadata["grading_eligible"] is False, text
        assert metadata["stt_quality"] == "uncertain", text
        assert "short_utterance" in metadata["uncertainty_reasons"], text
        assert "incomplete_fragment" in metadata["uncertainty_reasons"], text


def test_stt_rejection_reason_confirms_broken_english_can_pass(
    extension: MockLUVEExtension,
) -> None:
    cases = (
        "I go school yesterday",
        "She don't like coffee",
        "I am go to market",
        "I very like this lesson",
        "I want improve speaking",
    )
    for text in cases:
        analysis = _make_analysis(
            text,
            no_speech_prob=0.15,
            avg_logprob=-0.95,
        )
        reason = extension._stt_rejection_reason(
            analysis,
            is_final=True,
            audio_stats={"speech_ms": 1200},
        )
        assert reason is None, text

    uncertain_cases = (
        "I go school yesterday and she don't like coffee.",
        "Yesterday I eat rice and I am go to market.",
        "My friend don't speak English and I no understand this question.",
        "What you name and where you live?",
        "I very like this lesson but I no understand grammar.",
        "I want improve speaking because my English not good.",
    )
    for text in uncertain_cases:
        analysis = _make_analysis(
            text,
            no_speech_prob=0.42,
            avg_logprob=-1.18,
            word_confidences=[0.92, 0.88, 0.71, 0.75, 0.84, 0.78, 0.81, 0.69, 0.86, 0.83],
        )
        reason = extension._stt_rejection_reason(
            analysis,
            is_final=True,
            audio_stats={"speech_ms": 1500},
        )
        assert reason is None, text


def test_stt_rejection_reason_empty_and_noise_suppressed(
    extension: MockLUVEExtension,
) -> None:
    analysis_empty = _make_analysis(
        "",
        no_speech_prob=0.0,
        avg_logprob=0.0,
    )
    assert (
        extension._stt_rejection_reason(
            analysis_empty,
            is_final=True,
            audio_stats=None,
        )
        == "empty_transcript"
    )

    analysis_hallucination = _make_analysis(
        "Go home now, everyone. Go home now, everyone.",
        no_speech_prob=0.12,
        avg_logprob=-0.35,
    )
    assert extension._is_probable_stt_hallucination(
        analysis_hallucination.raw_text,
        is_final=True,
        audio_stats={"speech_ms": 1200},
        pcm_bytes=32000,
    ) is True

    weak_canned = _make_analysis(
        "Today is a club night.",
        no_speech_prob=0.18,
        avg_logprob=-0.52,
    )
    assert (
        extension._stt_rejection_reason(
            weak_canned,
            is_final=True,
            audio_stats={"speech_ms": 700},
        )
        == "probable_hallucination"
    )

    weak_thanks = _make_analysis(
        "Thank you very much.",
        no_speech_prob=0.20,
        avg_logprob=-0.50,
    )
    assert (
        extension._stt_rejection_reason(
            weak_thanks,
            is_final=True,
            audio_stats={"speech_ms": 800},
        )
        == "probable_hallucination"
    )


def test_vietnamese_suppression_and_learner_phrases(
    extension: MockLUVEExtension,
) -> None:
    assert extension._has_learner_english_evidence("hom nay troi dep qua") is False
    assert extension._has_learner_english_evidence("toi di hoc hom qua") is False
    assert extension._has_learner_english_evidence("xin chao ban") is False
    assert extension._has_learner_english_evidence("hôm nay trời đẹp quá") is False

    assert extension._has_learner_english_evidence("I go school yesterday") is True
    assert extension._has_learner_english_evidence("She don't like coffee") is True
    assert extension._has_learner_english_evidence("I want improve speaking") is True
    assert (
        extension._stt_rejection_reason(
            _make_analysis("yes", no_speech_prob=0.08, avg_logprob=-0.28),
            is_final=True,
            audio_stats={"speech_ms": 420},
        )
        is None
    )
    assert (
        extension._stt_rejection_reason(
            _make_analysis("no", no_speech_prob=0.08, avg_logprob=-0.28),
            is_final=True,
            audio_stats={"speech_ms": 420},
        )
        is None
    )
    assert (
        extension._stt_rejection_reason(
            _make_analysis("ok", no_speech_prob=0.08, avg_logprob=-0.32),
            is_final=True,
            audio_stats={"speech_ms": 420},
        )
        is None
    )

    assert extension._split_mixed_language_transcript("hom nay troi dep qua") == (
        "",
        ["mixed_non_english"],
    )
    assert extension._split_mixed_language_transcript(
        "Xin chào bạn, tôi đang kiểm tra hệ thống."
    ) == ("", ["mixed_non_english"])
    assert extension._split_mixed_language_transcript("Tôi đi học hôm nay") == (
        "",
        ["mixed_non_english"],
    )

    extracted, reasons = extension._split_mixed_language_transcript(
        "I want to practice tiếng Anh"
    )
    assert extracted == "I want to practice"
    assert reasons == ["mixed_language_filtered"]

    extracted, reasons = extension._split_mixed_language_transcript(
        "My name is Monty, tôi đang kiểm tra hệ thống"
    )
    assert extracted == "My name is Monty"
    assert reasons == ["mixed_language_filtered"]

    extracted, reasons = extension._split_mixed_language_transcript(
        "Can you help me, cảm ơn bạn"
    )
    assert extracted == "Can you help me"
    assert reasons == ["mixed_language_filtered"]

    extracted, reasons = extension._split_mixed_language_transcript(
        "Hello, hôm nay trời đẹp quá"
    )
    assert extracted == "Hello"
    assert reasons == ["weak_mixed_language_english"]

    extracted, reasons = extension._split_mixed_language_transcript(
        "What is, hôm nay trời đẹp quá"
    )
    assert extracted == "What is"
    assert reasons == ["weak_mixed_language_english"]

    assert (
        extension._stt_rejection_reason(
            _make_analysis("What is", no_speech_prob=0.08, avg_logprob=-0.30),
            is_final=True,
            audio_stats={"speech_ms": 760},
        )
        is None
    )


def test_mixed_language_filtered_metadata_preserves_original_text(
    extension: MockLUVEExtension,
) -> None:
    filtered = _make_analysis(
        "I want to practice",
        no_speech_prob=0.16,
        avg_logprob=-0.62,
        word_confidences=[0.92, 0.90, 0.91, 0.88],
    )
    metadata = extension._stt_quality_assessment(
        filtered,
        audio_stats={"speech_ms": 900, "audio_ms": 1300},
        inference_ms=85.0,
        original_text="I want to practice tiếng Anh",
        mixed_language_filtered=True,
    )
    assert metadata["stt_quality"] == "uncertain"
    assert metadata["original_stt_text"] == "I want to practice tiếng Anh"
    assert metadata["english_segment"] == "I want to practice"
    assert metadata["grading_eligible"] is True
    assert metadata["tutor_visible"] is True
    assert metadata["turn_language_type"] == "mixed"
    assert metadata["mixed_language"] is True
    assert metadata["removed_non_english"] is True
    assert "mixed_language_filtered" in metadata["uncertainty_reasons"]


def test_weak_mixed_fragment_metadata_is_tutor_visible_not_gradeable(
    extension: MockLUVEExtension,
) -> None:
    weak = _make_analysis(
        "What is",
        no_speech_prob=0.08,
        avg_logprob=-0.30,
    )
    metadata = extension._stt_quality_assessment(
        weak,
        audio_stats={"speech_ms": 760, "audio_ms": 1040},
        inference_ms=80.0,
        original_text="What is hôm nay trời đẹp quá",
        mixed_language_filtered=True,
        mixed_language_reasons=["weak_mixed_language_english"],
    )
    assert metadata["tutor_visible"] is True
    assert metadata["grading_eligible"] is False
    assert metadata["english_segment"] == ""
    assert metadata["excluded_from_grading_reason"] == "weak_mixed_language_english"
    assert "weak_mixed_language_english" in metadata["uncertainty_reasons"]


def test_final_acceptance_preserves_weak_mixed_and_uncertain_max_utterance(
    extension: MockLUVEExtension,
) -> None:
    weak_mixed = _make_analysis(
        "What is",
        no_speech_prob=0.08,
        avg_logprob=-0.30,
    )
    weak_metadata = extension._stt_quality_assessment(
        weak_mixed,
        audio_stats={"speech_ms": 760, "audio_ms": 1040},
        inference_ms=80.0,
        original_text="What is hôm nay trời đẹp quá",
        mixed_language_filtered=True,
        mixed_language_reasons=["weak_mixed_language_english"],
    )
    assert (
        extension._final_stt_acceptance_rejection_reason(
            weak_mixed,
            trigger="silence",
            audio_stats={"speech_ms": 760, "audio_ms": 1040},
            turn_metadata=weak_metadata,
            mixed_language_filtered=True,
        )
        is None
    )

    max_utterance = _make_analysis(
        "I want improve speaking because my English not good",
        no_speech_prob=0.22,
        avg_logprob=-0.72,
        word_confidences=[0.94, 0.91, 0.92, 0.90, 0.88, 0.87, 0.89, 0.90],
    )
    max_metadata = extension._stt_quality_assessment(
        max_utterance,
        audio_stats={"speech_ms": 6350, "audio_ms": 10430},
        inference_ms=180.0,
    )
    assert "low_average_logprob" in max_metadata["uncertainty_reasons"]
    assert (
        extension._final_stt_acceptance_rejection_reason(
            max_utterance,
            trigger="max_utterance",
            audio_stats={"speech_ms": 6350, "audio_ms": 10430},
            turn_metadata=max_metadata,
            mixed_language_filtered=False,
        )
        is None
    )

    valid_learner = _make_analysis(
        "I go school yesterday",
        no_speech_prob=0.12,
        avg_logprob=-0.48,
    )
    valid_metadata = extension._stt_quality_assessment(
        valid_learner,
        audio_stats={"speech_ms": 1200, "audio_ms": 1500},
        inference_ms=80.0,
    )
    assert (
        extension._final_stt_acceptance_rejection_reason(
            valid_learner,
            trigger="silence",
            audio_stats={"speech_ms": 1200, "audio_ms": 1500},
            turn_metadata=valid_metadata,
            mixed_language_filtered=False,
        )
        is None
    )


def test_non_english_verification_triggers_and_suppresses(
    extension: MockLUVEExtension,
) -> None:
    your_name = _make_analysis(
        "your name",
        no_speech_prob=0.10,
        avg_logprob=-0.40,
        word_confidences=[0.94, 0.95],
    )
    your_name_confidence = extension._stt_confidence_metrics(your_name)
    assert (
        extension._should_run_non_english_verification(
            your_name,
            audio_stats={"speech_ms": 760},
            confidence=your_name_confidence,
        )
        is False
    )

    suspicious = _make_analysis(
        "So they helped him out.",
        no_speech_prob=0.28,
        avg_logprob=-0.68,
        word_confidences=[0.91, 0.90, 0.89, 0.78, 0.74],
    )
    suspicious_confidence = extension._stt_confidence_metrics(suspicious)
    assert (
        extension._should_run_non_english_verification(
            suspicious,
            audio_stats={"speech_ms": 820},
            confidence=suspicious_confidence,
        )
        is True
    )

    verification_vi = _make_analysis(
        "Tôi đi học hôm nay",
        no_speech_prob=0.05,
        avg_logprob=-0.18,
    )
    verification_vi.detected_language = "vi"
    verification_vi.detected_language_probability = 0.93
    assert extension._verification_indicates_non_english(verification_vi) is True

    verification_en = _make_analysis(
        "your name",
        no_speech_prob=0.05,
        avg_logprob=-0.18,
    )
    verification_en.detected_language = "en"
    verification_en.detected_language_probability = 0.89
    assert extension._verification_indicates_non_english(verification_en) is False


def test_second_pass_verification_disabled_skips_worker_call(
    extension: MockLUVEExtension,
) -> None:
    suspicious = _make_analysis(
        "So they helped him out.",
        no_speech_prob=0.28,
        avg_logprob=-0.68,
        word_confidences=[0.91, 0.90, 0.89, 0.78, 0.74],
    )
    verification_en = _make_analysis(
        "So they helped him out.",
        no_speech_prob=0.06,
        avg_logprob=-0.20,
    )
    verification_en.detected_language = "en"
    verification_en.detected_language_probability = 0.91
    worker = FakeSTTWorker(verification_en)
    extension._stt_worker = worker
    extension._stt_second_pass_verification_enabled = False

    status, verification = asyncio.run(
        extension._verify_non_english_if_suspicious(
            analysis=suspicious,
            pcm_bytes=b"\0" * 48000,
            audio_stats={"speech_ms": 820},
            confidence=extension._stt_confidence_metrics(suspicious),
        )
    )

    assert status == "skipped"
    assert verification is None
    assert worker.calls == 0


def test_second_pass_verification_enabled_uses_existing_helper_behavior(
    extension: MockLUVEExtension,
) -> None:
    suspicious = _make_analysis(
        "So they helped him out.",
        no_speech_prob=0.28,
        avg_logprob=-0.68,
        word_confidences=[0.91, 0.90, 0.89, 0.78, 0.74],
    )
    verification_en = _make_analysis(
        "So they helped him out.",
        no_speech_prob=0.06,
        avg_logprob=-0.20,
    )
    verification_en.detected_language = "en"
    verification_en.detected_language_probability = 0.91
    worker = FakeSTTWorker(verification_en)
    extension._stt_worker = worker
    extension._stt_second_pass_verification_enabled = True

    status, verification = asyncio.run(
        extension._verify_non_english_if_suspicious(
            analysis=suspicious,
            pcm_bytes=b"\0" * 48000,
            audio_stats={"speech_ms": 820},
            confidence=extension._stt_confidence_metrics(suspicious),
        )
    )

    assert status == "verified"
    assert verification is verification_en
    assert worker.calls == 1


def test_verification_unavailable_marks_turn_uncertain(
    extension: MockLUVEExtension,
) -> None:
    analysis = _make_analysis(
        "I go to school yesterday",
        no_speech_prob=0.18,
        avg_logprob=-0.60,
        word_confidences=[0.94, 0.93, 0.94, 0.92, 0.95],
    )
    metadata = extension._stt_quality_assessment(
        analysis,
        audio_stats={"speech_ms": 1200, "audio_ms": 1500},
        inference_ms=88.0,
        verification_status="unavailable",
    )
    assert metadata["stt_quality"] == "uncertain"
    assert "verification_unavailable" in metadata["uncertainty_reasons"]


def test_whisper_hallucination_suppression(extension: MockLUVEExtension) -> None:
    assert (
        extension._is_probable_stt_hallucination(
            "Go home now, everyone. Go home now, everyone.",
            is_final=True,
            audio_stats={"speech_ms": 1200},
            pcm_bytes=48000,
        )
        is True
    )

    assert (
        extension._is_probable_stt_hallucination(
            "Thank you very much. Thank you very much.",
            is_final=True,
            audio_stats={"speech_ms": 1500},
            pcm_bytes=64000,
        )
        is True
    )

    assert (
        extension._is_probable_stt_hallucination(
            "Today is a club night.",
            is_final=True,
            audio_stats={"speech_ms": 1200},
            pcm_bytes=48000,
        )
        is True
    )

    assert (
        extension._is_probable_stt_hallucination(
            "I don't know what to say.",
            is_final=True,
            audio_stats={"speech_ms": 900},
            pcm_bytes=30000,
        )
        is True
    )

    assert (
        extension._is_probable_stt_hallucination(
            "Thank you very much.",
            is_final=True,
            audio_stats={"speech_ms": 1200},
            pcm_bytes=30000,
        )
        is True
    )

    analysis_weak_tyvm = _make_analysis(
        "Thank you very much.",
        no_speech_prob=0.15,
        avg_logprob=-0.85,
    )
    reason = extension._stt_rejection_reason(
        analysis_weak_tyvm,
        is_final=True,
        audio_stats={"speech_ms": 1800},
    )
    assert reason == "probable_hallucination"

    assert (
        extension._is_probable_stt_hallucination(
            "Thank you very much.",
            is_final=True,
            audio_stats={"speech_ms": 1800},
            pcm_bytes=64000,
        )
        is False
    )

    analysis_strong_tyvm = _make_analysis(
        "Thank you very much.",
        no_speech_prob=0.02,
        avg_logprob=-0.20,
    )
    reason = extension._stt_rejection_reason(
        analysis_strong_tyvm,
        is_final=True,
        audio_stats={"speech_ms": 1800},
    )
    assert reason is None

    for text in (
        "I go school yesterday",
        "She don't like coffee",
        "I am go to market",
        "I very like this lesson",
    ):
        assert (
            extension._is_probable_stt_hallucination(
                text,
                is_final=True,
                audio_stats={"speech_ms": 1500},
                pcm_bytes=60000,
            )
            is False
        )
