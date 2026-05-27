from __future__ import annotations
import pytest
from src.schemas.ai_logic import STTAnalysis
from src.ten_ext.luve_extension import LUVEExtension, COMMON_ENGLISH_WORDS

class MockLUVEExtension(LUVEExtension):
    """Subclass of LUVEExtension to isolate and test helper logic statically

    without invoking super().__init__() which requires the TEN extension environment.
    """
    def __init__(self) -> None:
        self._stt_final_min_speech_ms = 180

@pytest.fixture()
def extension() -> MockLUVEExtension:
    # Use a mock class where __init__ is safely overridden to bypass TEN extension library load
    return MockLUVEExtension()

def test_is_english_like_utterance(extension: MockLUVEExtension) -> None:
    # Helper functions
    assert extension._english_token_count("I go school yesterday") == 4
    assert extension._english_token_count("") == 0

    assert extension._has_learner_english_evidence("I go school yesterday") is True
    assert extension._has_learner_english_evidence("she don't like coffee") is True
    assert extension._has_learner_english_evidence("yes please") is True
    assert extension._has_learner_english_evidence("hôm nay tôi đi học") is False
    assert extension._has_learner_english_evidence("") is False
    # Single words are not considered phrase evidence (require >= 2 words)
    assert extension._has_learner_english_evidence("yes") is False

def test_is_strong_short_english_response(extension: MockLUVEExtension) -> None:
    # Valid yes/no/ok/okay short responses with strong evidence
    conf_ok = {"word_count": 1, "low_confidence_word_ratio": 0.10}
    conf_poor = {"word_count": 1, "low_confidence_word_ratio": 0.40}

    # Strong yes response
    analysis_yes = STTAnalysis(
        raw_text="yes",
        no_speech_prob=0.05,
        avg_logprob=-0.25,
        compression_ratio=1.0,
        words=[]
    )
    assert extension._is_strong_short_english_response(analysis_yes, {"speech_ms": 400}, conf_ok) is True

    # Poor no speech probability
    analysis_poor_ns = STTAnalysis(
        raw_text="yes",
        no_speech_prob=0.80,
        avg_logprob=-0.25,
        compression_ratio=1.0,
        words=[]
    )
    assert extension._is_strong_short_english_response(analysis_poor_ns, {"speech_ms": 400}, conf_ok) is False

    # Short speech duration (< 350ms)
    assert extension._is_strong_short_english_response(analysis_yes, {"speech_ms": 200}, conf_ok) is False

    # Poor avg logprob
    analysis_poor_logprob = STTAnalysis(
        raw_text="yes",
        no_speech_prob=0.05,
        avg_logprob=-0.70,
        compression_ratio=1.0,
        words=[]
    )
    assert extension._is_strong_short_english_response(analysis_poor_logprob, {"speech_ms": 400}, conf_ok) is False

    # Poor word confidence
    assert extension._is_strong_short_english_response(analysis_yes, {"speech_ms": 400}, conf_poor) is False

def test_stt_rejection_reason_grammatically_broken_english(extension: MockLUVEExtension) -> None:
    # A grammatically broken phrase that would be suppressed under the old strict avg_logprob (-0.65)
    # but passes under the new relaxed rules
    analysis = STTAnalysis(
        raw_text="I go school yesterday",
        no_speech_prob=0.15,
        avg_logprob=-0.95,
        compression_ratio=1.0,
        words=[]
    )
    reason = extension._stt_rejection_reason(
        analysis,
        is_final=True,
        audio_stats={"speech_ms": 1200}
    )
    assert reason is None

def test_stt_rejection_reason_empty_and_noise_suppressed(extension: MockLUVEExtension) -> None:
    # Empty transcript rejection
    analysis_empty = STTAnalysis(raw_text="", no_speech_prob=0.0, avg_logprob=0.0, compression_ratio=1.0, words=[])
    assert extension._stt_rejection_reason(analysis_empty, is_final=True, audio_stats=None) == "empty_transcript"

    # Vietnamese phonetic nonsense
    analysis_vi = STTAnalysis(
        raw_text="hom nay toy dee hoc",
        no_speech_prob=0.20,
        avg_logprob=-1.30,
        compression_ratio=1.0,
        words=[]
    )
    reason = extension._stt_rejection_reason(
        analysis_vi,
        is_final=True,
        audio_stats={"speech_ms": 1500}
    )
    assert reason in ("no_english_evidence", "low_average_logprob")

    # One random hallucinated English token "you" with bad confidence
    analysis_you = STTAnalysis(
        raw_text="you",
        no_speech_prob=0.90,
        avg_logprob=-1.40,
        compression_ratio=1.0,
        words=[]
    )
    reason = extension._stt_rejection_reason(
        analysis_you,
        is_final=True,
        audio_stats={"speech_ms": 400}
    )
    # Fails because word count < 2 (not phrase), and does not match "strong short respond allowed list" (only yes/no/ok/okay)
    # and has poor acoustic confidence. So strict thresholds apply.
    assert reason in ("high_no_speech_probability", "low_average_logprob", "too_few_words", "low_speech_duration")


def test_vietnamese_suppression_and_learner_phrases(extension: MockLUVEExtension) -> None:
    # 1. Suppress likely forced-English Vietnamese phonetic outputs:
    assert extension._has_learner_english_evidence("hom nay troi dep qua") is False
    assert extension._has_learner_english_evidence("toi di hoc") is False
    assert extension._has_learner_english_evidence("xin chao ban") is False
    assert extension._has_learner_english_evidence("hôm nay trời đẹp quá") is False

    # 2. Keep tests that must pass:
    assert extension._has_learner_english_evidence("I go school yesterday") is True
    assert extension._has_learner_english_evidence("She don't like coffee") is True
    assert extension._has_learner_english_evidence("I want improve speaking") is True

    # Strong short answers yes/no/ok/okay pass acoustic checks
    analysis_yes = STTAnalysis(
        raw_text="yes",
        no_speech_prob=0.05,
        avg_logprob=-0.25,
        compression_ratio=1.0,
        words=[]
    )
    conf_ok = {"word_count": 1, "low_confidence_word_ratio": 0.10}
    assert extension._is_strong_short_english_response(analysis_yes, {"speech_ms": 400}, conf_ok) is True

    # Strict rejection of pure Vietnamese speech from passing as eligible learner English
    analysis_vi_phrase = STTAnalysis(
        raw_text="hom nay troi dep qua",
        no_speech_prob=0.10,
        avg_logprob=-0.35,  # high average logprob
        compression_ratio=1.0,
        words=[]
    )
    reason = extension._stt_rejection_reason(
        analysis_vi_phrase,
        is_final=True,
        audio_stats={"speech_ms": 1200}
    )
    assert reason == "no_english_evidence"


def test_whisper_hallucination_suppression(extension: MockLUVEExtension) -> None:
    # 1. Repetitive loops should be suppressed
    assert extension._is_probable_stt_hallucination(
        "Go home now, everyone. Go home now, everyone.",
        is_final=True,
        audio_stats={"speech_ms": 1200},
        pcm_bytes=48000
    ) is True

    assert extension._is_probable_stt_hallucination(
        "Thank you very much. Thank you very much.",
        is_final=True,
        audio_stats={"speech_ms": 1500},
        pcm_bytes=64000
    ) is True

    # 2. Canned phrases with weak/poor audio/metrics should be suppressed
    assert extension._is_probable_stt_hallucination(
        "Today is a club night.",
        is_final=True,
        audio_stats={"speech_ms": 1200},
        pcm_bytes=48000
    ) is True

    # "Thank you very much" with short audio / speech_ms is suppressed in _is_probable_stt_hallucination
    assert extension._is_probable_stt_hallucination(
        "Thank you very much.",
        is_final=True,
        audio_stats={"speech_ms": 1200},
        pcm_bytes=30000  # 1.875 seconds
    ) is True

    # "Thank you very much" with weak confidence metrics is suppressed in _stt_rejection_reason
    analysis_weak_tyvm = STTAnalysis(
        raw_text="Thank you very much.",
        no_speech_prob=0.15,
        avg_logprob=-0.85,  # poor logprob
        compression_ratio=1.0,
        words=[]
    )
    reason = extension._stt_rejection_reason(
        analysis_weak_tyvm,
        is_final=True,
        audio_stats={"speech_ms": 1800}
    )
    assert reason == "probable_hallucination"

    # 3. Genuine "Thank you very much" with strong metrics must NOT be suppressed
    assert extension._is_probable_stt_hallucination(
        "Thank you very much.",
        is_final=True,
        audio_stats={"speech_ms": 1800},
        pcm_bytes=64000  # 4.0s
    ) is False

    analysis_strong_tyvm = STTAnalysis(
        raw_text="Thank you very much.",
        no_speech_prob=0.02,
        avg_logprob=-0.20,  # excellent logprob
        compression_ratio=1.0,
        words=[]
    )
    reason = extension._stt_rejection_reason(
        analysis_strong_tyvm,
        is_final=True,
        audio_stats={"speech_ms": 1800}
    )
    assert reason is None

    # 4. Valid grammatically broken learner phrases must NOT be suppressed
    assert extension._is_probable_stt_hallucination(
        "I go school yesterday",
        is_final=True,
        audio_stats={"speech_ms": 1500},
        pcm_bytes=60000
    ) is False

    assert extension._is_probable_stt_hallucination(
        "She don't like coffee",
        is_final=True,
        audio_stats={"speech_ms": 1500},
        pcm_bytes=60000
    ) is False

    assert extension._is_probable_stt_hallucination(
        "I am go to market",
        is_final=True,
        audio_stats={"speech_ms": 1500},
        pcm_bytes=60000
    ) is False

    assert extension._is_probable_stt_hallucination(
        "My friend don't speak English",
        is_final=True,
        audio_stats={"speech_ms": 1800},
        pcm_bytes=72000
    ) is False

    assert extension._is_probable_stt_hallucination(
        "I very like this lesson",
        is_final=True,
        audio_stats={"speech_ms": 1500},
        pcm_bytes=60000
    ) is False


