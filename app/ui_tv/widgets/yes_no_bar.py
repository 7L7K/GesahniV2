"""Yes/No bar scaffold."""

from dataclasses import dataclass


@dataclass
class YesNoBarModel:
    yes_label: str = "Yes"
    no_label: str = "No"
    is_visible: bool = False


