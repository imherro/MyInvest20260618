"""Universe configuration for TenBagger research runs."""

from __future__ import annotations


VALID_UNIVERSE_LEVELS = ("dev", "research", "production")

UNIVERSE_TARGETS = {
    "dev": 50,
    "research": 500,
    "production": None,
}

RESEARCH_MIN_STOCKS = 300
RESEARCH_MAX_STOCKS = 1000

# Small local fallback used only when a developer machine cannot reach TuShare.
# Research and production universes must come from the UniverseManager provider.
DEBUG_FALLBACK_UNIVERSE = [
    "000001.SZ",
    "000651.SZ",
    "000858.SZ",
    "002415.SZ",
    "002594.SZ",
    "300750.SZ",
    "600000.SH",
    "600519.SH",
    "600887.SH",
    "601318.SH",
    "603259.SH",
    "688981.SH",
]
