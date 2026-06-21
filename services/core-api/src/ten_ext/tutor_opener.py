"""Static, A1-friendly opening greetings for the realtime tutor.

The tutor (persona "Lucy", defined in ``src/media/brain.py``) proactively greets
the learner once when a practice session becomes ready, so the learner does not
have to speak first. Each opener is English-only, short, and asks exactly one
easy (A1) question. Selection rotates deterministically by index so successive
sessions vary without an immediate repeat.
"""
from __future__ import annotations

# Each opener: English only, short (<= 12 words), exactly one question, A1 level.
# "Lucy" matches the tutor persona defined in src/media/brain.py.
OPENERS: tuple[str, ...] = (
    "Hi, I'm Lucy. What is your name?",
    "Hello! How are you today?",
    "Hi! Where are you from?",
    "Hello! What food do you like?",
    "Hi! What color do you like?",
    "Hello! Do you like music?",
    "Hi! Are you ready to practice?",
)


def pick_opener(index: int) -> str:
    """Return one opener, rotating deterministically by index.

    Any integer is accepted; selection wraps around the list so callers can keep
    a simple incrementing counter without bounds-checking.
    """
    return OPENERS[index % len(OPENERS)]
