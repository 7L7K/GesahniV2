import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.intent_detector import detect_intent


def test_short_greeting_classification():
    assert detect_intent("hi") == ("smalltalk", "low")
    assert detect_intent("hello") == ("smalltalk", "low")
