"""Confirmation screen scaffold.

Shows "Did you mean …?" and presents Yes/No options.
"""

from dataclasses import dataclass


@dataclass
class ConfirmationModel:
    prompt_text: str
    options: tuple[str, str] = ("Yes", "No")


def build_confirmation(prompt_text: str) -> ConfirmationModel:
    return ConfirmationModel(prompt_text=prompt_text)
