"""Tutor conversation policy: context-aware, answer-first, level-adaptive.

These guard the SYSTEM_PROMPT against regressing the behavior rules that make
the tutor answer direct learner questions with concrete suggestions (using
recent context) instead of chaining vague questions back.
"""

from src.media.brain import LLMProcessor


def test_system_prompt_answers_direct_questions_first():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    assert "answer" in p
    assert "first" in p
    # concrete/specific suggestions, not vague questions
    assert "concrete" in p or "specific" in p


def test_system_prompt_uses_recent_context_and_avoids_repeats():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    assert "recent conversation" in p or "context" in p
    # do not re-ask information the learner already gave
    assert "already" in p


def test_system_prompt_limits_followups_and_adapts_level():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    assert "follow-up" in p or "follow up" in p
    assert "at most one" in p
    assert "level" in p or "simple" in p


def test_system_prompt_keeps_english_and_output_contract():
    p = LLMProcessor.SYSTEM_PROMPT
    # tutor conversation stays in English
    assert "English" in p
    # parser depends on the 2-line output labels — must not break
    assert "RESPONSE_TEXT:" in p
    assert "PEDAGOGICAL_FEEDBACK:" in p
