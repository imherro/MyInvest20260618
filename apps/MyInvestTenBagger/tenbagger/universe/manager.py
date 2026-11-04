"""Single source of truth for stock-universe selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from tenbagger.universe.config import (
    DEBUG_FALLBACK_UNIVERSE,
    RESEARCH_MAX_STOCKS,
    RESEARCH_MIN_STOCKS,
    UNIVERSE_TARGETS,
    VALID_UNIVERSE_LEVELS,
)
from tenbagger.universe.filters import apply_universe_filters
from tenbagger.universe.provider import DebugFallbackProvider, TushareUniverseProvider, UniverseProvider


@dataclass(frozen=True)
class UniverseSnapshot:
    level: str
    codes: list[str]
    source: str
    filter_stats: dict[str, int]
    target_size: int | None

    def to_api(self) -> dict:
        payload = asdict(self)
        payload["stock_count"] = len(self.codes)
        payload["sample"] = self.codes[:20]
        return payload


class UniverseManager:
    """Build dev, research, and production universes from one provider path."""

    def __init__(self, provider: UniverseProvider | None = None) -> None:
        self.provider = provider or TushareUniverseProvider()

    @classmethod
    def get(cls, level: str = "dev", provider: UniverseProvider | None = None) -> list[str]:
        """Return only the ts_code list for the requested universe level."""

        return cls(provider=provider).resolve(level).codes

    @classmethod
    def get_details(cls, level: str = "dev", provider: UniverseProvider | None = None) -> dict:
        """Return metadata suitable for CLI/API display."""

        return cls(provider=provider).resolve(level).to_api()

    def resolve(self, level: str = "dev") -> UniverseSnapshot:
        normalized_level = _normalize_level(level)
        try:
            raw = self.provider.stock_basic()
            source = getattr(self.provider, "source", self.provider.__class__.__name__)
        except Exception:
            if normalized_level != "dev":
                raise
            raw = DebugFallbackProvider().stock_basic()
            source = DebugFallbackProvider.source

        filtered = apply_universe_filters(raw)
        selected = self._select_codes(filtered.frame, normalized_level)
        return UniverseSnapshot(
            level=normalized_level,
            codes=selected,
            source=source,
            filter_stats=filtered.stats,
            target_size=UNIVERSE_TARGETS[normalized_level],
        )

    @staticmethod
    def _select_codes(frame: pd.DataFrame, level: str) -> list[str]:
        codes = frame["ts_code"].dropna().astype(str).str.strip().tolist()
        codes = list(dict.fromkeys(code for code in codes if code))

        if level == "dev":
            seed = [code for code in DEBUG_FALLBACK_UNIVERSE if code in set(codes)]
            remainder = [code for code in codes if code not in set(seed)]
            return list(dict.fromkeys(seed + remainder))[: UNIVERSE_TARGETS["dev"]]

        if level == "research":
            capped = codes[:RESEARCH_MAX_STOCKS]
            target = min(UNIVERSE_TARGETS["research"], len(capped))
            selected = capped[:target]
            if len(selected) < RESEARCH_MIN_STOCKS:
                raise ValueError(
                    f"Research universe requires at least {RESEARCH_MIN_STOCKS} stocks; got {len(selected)}."
                )
            return selected

        return codes


def filter_frame_to_universe(frame: pd.DataFrame, universe: Iterable[str] | None) -> pd.DataFrame:
    """Filter a dataframe by ts_code while preserving non-stock frames as-is."""

    if universe is None or frame.empty or "ts_code" not in frame:
        return frame.copy()

    allowed = {str(code).strip().upper() for code in universe if str(code).strip()}
    if not allowed:
        return frame.iloc[0:0].copy()
    mask = frame["ts_code"].astype(str).str.strip().str.upper().isin(allowed)
    return frame[mask].copy()


def _normalize_level(level: str) -> str:
    normalized = str(level or "dev").strip().lower()
    if normalized not in VALID_UNIVERSE_LEVELS:
        raise ValueError(f"Unsupported universe level: {level}. Expected one of {VALID_UNIVERSE_LEVELS}.")
    return normalized
