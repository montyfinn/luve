"""Focused tests for the static, A1-friendly tutor opening greetings.

Pure module: no runtime, DB, or network. Validates the opener list shape and
the deterministic rotation used so successive sessions vary.
"""
from __future__ import annotations

from src.ten_ext.tutor_opener import OPENERS, pick_opener

# Accented characters that would indicate non-English (Vietnamese) text.
_VIETNAMESE_ACCENTED = set(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ĂÂĐÊÔƠƯ"
)


def test_openers_are_present_and_non_empty() -> None:
    assert len(OPENERS) >= 3
    for opener in OPENERS:
        assert opener.strip(), "opener must be non-empty"


def test_openers_are_english_only() -> None:
    for opener in OPENERS:
        # English-only: plain ASCII, no Vietnamese accented characters.
        assert opener.isascii(), opener
        assert not (set(opener) & _VIETNAMESE_ACCENTED), opener


def test_openers_are_short_and_a1_friendly() -> None:
    for opener in OPENERS:
        word_count = len(opener.split())
        assert 3 <= word_count <= 12, f"{opener!r} has {word_count} words"


def test_each_opener_asks_exactly_one_question() -> None:
    for opener in OPENERS:
        assert opener.count("?") == 1, opener
        # The question is the final clause, so the opener ends with "?".
        assert opener.rstrip().endswith("?"), opener


def test_persona_intro_uses_existing_lucy_name_not_luve() -> None:
    # The product already defines a tutor persona "Lucy" (brain.py); the opener
    # list must stay consistent and must not introduce a different name.
    assert any("Lucy" in opener for opener in OPENERS)
    assert not any("LUVE" in opener for opener in OPENERS)


def test_pick_opener_rotates_deterministically_and_wraps() -> None:
    assert pick_opener(0) == OPENERS[0]
    assert pick_opener(1) == OPENERS[1]
    # Wraps around without bounds errors.
    assert pick_opener(len(OPENERS)) == OPENERS[0]
    assert pick_opener(len(OPENERS) + 1) == OPENERS[1]


def test_pick_opener_covers_every_opener_over_a_full_cycle() -> None:
    seen = {pick_opener(i) for i in range(len(OPENERS))}
    assert seen == set(OPENERS)
