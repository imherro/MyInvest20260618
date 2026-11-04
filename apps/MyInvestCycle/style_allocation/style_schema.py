from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class StyleDefinition:
    style_id: str
    label: str
    role: str
    representative_assets: tuple[dict[str, str], ...]
    description: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["representative_assets"] = [dict(item) for item in self.representative_assets]
        return payload


STYLE_UNIVERSE: tuple[StyleDefinition, ...] = (
    StyleDefinition(
        "growth",
        "Growth",
        "offensive",
        (
            {"code": "159915.SZ", "name": "创业板ETF"},
            {"code": "588000.SH", "name": "科创50ETF"},
            {"code": "512480.SH", "name": "半导体ETF"},
        ),
        "成长/科技风格，主要观察创业板、科创和半导体方向的趋势与拥挤风险。",
    ),
    StyleDefinition(
        "small_cap",
        "Small Cap",
        "offensive",
        (
            {"code": "510500.SH", "name": "中证500ETF"},
            {"code": "512100.SH", "name": "中证1000ETF"},
        ),
        "中小盘风格，主要观察市场宽度和中小市值相对强弱。",
    ),
    StyleDefinition(
        "value",
        "Value",
        "core",
        (
            {"code": "510300.SH", "name": "沪深300ETF"},
            {"code": "510050.SH", "name": "上证50ETF"},
        ),
        "价值/大盘风格，作为宽基核心 Beta 与阶段防守过渡风格。",
    ),
    StyleDefinition(
        "dividend",
        "Dividend",
        "defensive",
        (
            {"code": "510880.SH", "name": "红利ETF"},
            {"code": "512890.SH", "name": "红利低波ETF"},
        ),
        "红利/低波风格，主要承担防守、波动缓冲和拥挤风险对冲观察。",
    ),
)


STYLE_IDS: tuple[str, ...] = tuple(item.style_id for item in STYLE_UNIVERSE)

CODE_TO_STYLE: dict[str, str] = {
    asset["code"]: style.style_id
    for style in STYLE_UNIVERSE
    for asset in style.representative_assets
}

BUCKET_TO_STYLE: dict[str, str] = {
    "growth_technology": "growth",
    "new_energy": "growth",
    "mid_small": "small_cap",
    "value_large": "value",
    "financial_value": "value",
    "dividend_defensive": "dividend",
}


def style_universe_payload() -> list[dict[str, object]]:
    return [style.to_dict() for style in STYLE_UNIVERSE]


def style_for_asset_code(code: str) -> str | None:
    return CODE_TO_STYLE.get(str(code))


def style_for_bucket(bucket: str) -> str | None:
    return BUCKET_TO_STYLE.get(str(bucket))


def empty_style_scores(value: float = 0.0) -> dict[str, float]:
    return {style_id: float(value) for style_id in STYLE_IDS}


def normalize_signal_share(scores: Mapping[str, float]) -> dict[str, float]:
    positive = {style_id: max(0.0, float(scores.get(style_id, 0.0))) for style_id in STYLE_IDS}
    total = sum(positive.values())
    if total <= 0:
        return {style_id: round(1.0 / len(STYLE_IDS), 6) for style_id in STYLE_IDS}
    rounded = {style_id: round(positive[style_id] / total, 6) for style_id in STYLE_IDS}
    drift = round(1.0 - sum(rounded.values()), 6)
    if drift:
        largest = max(rounded, key=rounded.get)
        rounded[largest] = round(rounded[largest] + drift, 6)
    return rounded
