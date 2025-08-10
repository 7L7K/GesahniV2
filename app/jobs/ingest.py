from __future__ import annotations

import re
from typing import Iterable

from dateutil import parser as dateparser

from app.adapters.memory import mem


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentence_chunks(text: str) -> Iterable[str]:
    """Yield 1–3 sentence chunks from *text*."""
    sentences = _SENT_SPLIT_RE.split(text.strip())
    buf: list[str] = []
    for sent in sentences:
        if not sent:
            continue
        buf.append(sent.strip())
        if len(buf) == 3:
            yield " ".join(buf)
            buf = []
    if buf:
        yield " ".join(buf)


_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b")
_DATE_RE = re.compile(r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b")


def _extract_people(text: str) -> list[str]:
    return _NAME_RE.findall(text)


def _extract_dates(text: str) -> list[str]:
    out: list[str] = []
    for raw in _DATE_RE.findall(text):
        try:
            dt = dateparser.parse(raw)
        except Exception:
            continue
        out.append(dt.date().isoformat())
    return out


def ingest_transcript(transcript: str, user_id: str) -> None:
    """Ingest a raw transcript for *user_id* into the memory backend."""
    for chunk in _sentence_chunks(transcript):
        mem_id = mem.add(user_id, chunk)
        for person in _extract_people(chunk):
            pid = mem.upsert_entity("person", person)
            mem.link(mem_id, "mentions", pid)
        for date in _extract_dates(chunk):
            did = mem.upsert_entity("date", date)
            mem.link(mem_id, "mentions", did)
