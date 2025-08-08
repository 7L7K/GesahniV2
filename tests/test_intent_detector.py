import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from app.intent_detector import Priority, detect_intent


@pytest.mark.parametrize(
    "text, expected",
    [
        ("yo", ("smalltalk", "low")),
        ("hello there", ("smalltalk", "low")),
        ("turn on the lights", ("control", "high")),
        ("tell me a fun fact", ("chat", "medium")),
        ("asdasdasd", ("unknown", "low")),
    ],
)
def test_detect_intent_cases(text: str, expected: tuple[str, Priority]) -> None:
    assert detect_intent(text) == expected
