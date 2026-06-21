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


def test_system_prompt_respects_topic_boundaries_and_switches():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    assert "latest learner message controls" in p
    assert "do not force the old topic back" in p
    assert "don't talk about" in p
    assert "change topic" in p
    assert "do not talk about or mention the avoided topic again" in p
    assert "new topic" in p


def test_system_prompt_handles_direct_meta_question_briefly():
    p = LLMProcessor.SYSTEM_PROMPT
    assert "What can you do?" in p
    assert "What do you do?" in p
    assert "How can you help me?" in p
    assert "I can help you practice English conversation" in p
    assert "What would you like to practice?" in p
    assert "no more than 2 short sentences" in p


def test_system_prompt_avoids_long_recaps():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    assert "avoid long recaps" in p
    assert "do not summarize many past turns" in p


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


def test_system_prompt_avoids_overconfident_local_claims():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    # warn against asserting local/cultural facts unless confident
    assert "local" in p or "cultural" in p
    assert "confident" in p or "unsure" in p or "uncertain" in p
    # the specific risky pattern that caused a hallucination ("X popular in <place>")
    assert "popular in" in p


def test_system_prompt_uses_soft_wording_when_unsure():
    p = LLMProcessor.SYSTEM_PROMPT
    # at least one hedging phrase is offered for uncertain recommendations
    assert "You could try" in p or "A safe idea is" in p
    # prefer suggestions grounded in the conversation over risky factual claims
    assert "grounded" in p.lower()


def test_system_prompt_rephrases_on_clarification_request():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    # "What?"/"Sorry?"/"can you repeat" must make the tutor rephrase its
    # previous question, not answer as if asked a question about itself.
    assert "rephrase" in p
    assert "what?" in p or "sorry?" in p or "repeat" in p
    assert "previous question" in p


def test_system_prompt_closes_on_goodbye_without_new_question():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    # goodbye / "I'm tired" must get a short closing, not a new question.
    assert "goodbye" in p
    assert "closing" in p
    assert "do not ask a new question" in p


def test_system_prompt_clarification_restates_tutor_own_question():
    p = LLMProcessor.SYSTEM_PROMPT.lower()
    # On "What?"/"Sorry?" the tutor must restate ITS OWN question (e.g. begin
    # "I asked: ..."), not summarize what the learner previously said.
    assert "i asked:" in p
    assert "do not summarize" in p
