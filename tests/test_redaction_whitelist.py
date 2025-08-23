from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _contacts_tmp(monkeypatch, tmp_path: Path):
    contacts = [
        {"name": "Alice", "phone": "+1 (555) 123-4567"},
        {"name": "Bob", "phone": "555-987-6543"},
    ]
    f = tmp_path / "contacts.json"
    f.write_text(json.dumps(contacts), encoding="utf-8")
    monkeypatch.setenv("CONTACTS_FILE", str(f))
    yield


def test_redaction_skips_whitelisted_numbers(monkeypatch):
    from app.redaction import redact_pii

    text = "Call me at 555-123-4567 or 555-000-1111"
    red, mapping = redact_pii(
        text, whitelist_numbers=["+1 555-123-4567", "5551234567"]
    )  # normalized match
    assert "555-123-4567" in red  # whitelisted number remains
    # Non-whitelisted is redacted
    assert any(k in red for k in mapping.keys())
