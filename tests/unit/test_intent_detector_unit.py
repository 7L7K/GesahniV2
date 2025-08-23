import pytest


@pytest.mark.parametrize(
    "prompt,expected_intent",
    [
        ("hello there", "smalltalk"),
        ("turn on the lights", "control"),
        ("what did i say yesterday?", "recall_story"),
        ("asdfgh", "unknown"),
    ],
)
def test_detect_intent_basic(prompt, expected_intent):
    from app.intent_detector import detect_intent

    intent, priority = detect_intent(prompt)
    assert intent == expected_intent
    assert priority in {"low", "medium", "high"}


@pytest.mark.parametrize(
    "prompt,threshold",
    [
        ("tell me a joke", 0.9),
        ("do you know a random fact?", 0.8),
        ("say something interesting", 0.6),
    ],
)
def test_detect_intent_thresholding(prompt, threshold):
    from app.intent_detector import detect_intent

    intent, priority = detect_intent(prompt, threshold=threshold)
    assert intent in {"chat", "unknown", "smalltalk", "control", "recall_story"}
