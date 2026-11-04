from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

import requests


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


@dataclass
class WebEvidenceProvider:
    timeout: int = 10
    max_chars: int = 1200

    def fetch_text_preview(self, url: str) -> dict[str, str]:
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "MyShortTerm/0.1"})
        response.raise_for_status()
        parser = _TextExtractor()
        parser.feed(response.text)
        text = " ".join(parser.parts)
        return {
            "url": url,
            "title_or_text": text[: self.max_chars],
        }

