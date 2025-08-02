# app/skills/news_skill.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx

from .base import Skill


class NewsSkill(Skill):
    PATTERNS = [
        re.compile(r"top\s+\d+\s+headlines", re.I),
        re.compile(r"top\s+headlines", re.I),
        re.compile(r"news", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        feed_url = "https://news.ycombinator.com/rss"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()
            xml_text = resp.text
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")[:3]
        titles = [item.findtext("title") for item in items if item.findtext("title")]
        if not titles:
            return "No headlines found."
        return "\n".join(f"{i+1}. {title}" for i, title in enumerate(titles))
