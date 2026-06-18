"""Tutor conversation context window (sliding window of recent turns)."""

from src.media.brain import LLMProcessor
from src.schemas.ai_logic import STTAnalysis


def _proc() -> LLMProcessor:
    return LLMProcessor(api_key="x", provider="groq")


def test_format_history_empty_returns_blank():
    assert LLMProcessor._format_history(None) == ""
    assert LLMProcessor._format_history([]) == ""


def test_format_history_renders_labeled_turns_in_order():
    out = LLMProcessor._format_history(
        [
            {"speaker": "learner", "text": "i go to school yesterday"},
            {"speaker": "tutor", "text": "Nice! Where is your school?"},
        ]
    )
    assert out.startswith("Recent conversation (most recent last):\n")
    assert "Learner: i go to school yesterday" in out
    assert "Lucy: Nice! Where is your school?" in out
    assert out.endswith("\n\n")
    # learner turn appears before tutor turn
    assert out.index("Learner: i go") < out.index("Lucy: Nice")


def test_format_history_skips_empty_text():
    out = LLMProcessor._format_history(
        [{"speaker": "learner", "text": "  "}, {"speaker": "tutor", "text": "Hi"}]
    )
    assert "Learner:" not in out
    assert "Lucy: Hi" in out


def test_build_user_prompt_prepends_history():
    proc = _proc()
    stt = STTAnalysis(raw_text="i like coffee")
    history = [
        {"speaker": "learner", "text": "hello"},
        {"speaker": "tutor", "text": "Hi there, how are you?"},
    ]
    prompt = proc._build_user_prompt(stt, history=history)
    assert "Recent conversation (most recent last):" in prompt
    # history must come before the current learner transcript
    assert prompt.index("Recent conversation") < prompt.index("Learner transcript:")
    assert "Lucy: Hi there, how are you?" in prompt
    assert "Learner transcript:\ni like coffee" in prompt


def test_build_user_prompt_without_history_unchanged():
    proc = _proc()
    stt = STTAnalysis(raw_text="i like coffee")
    prompt = proc._build_user_prompt(stt)
    assert "Recent conversation" not in prompt
    assert prompt.startswith("Learner transcript:")
