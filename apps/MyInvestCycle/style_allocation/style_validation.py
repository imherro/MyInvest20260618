from __future__ import annotations

from bisect import bisect_right
from typing import Mapping

from style_allocation.style_schema import STYLE_IDS, normalize_signal_share, style_for_asset_code


VALIDATION_STATES = ("BROAD_BULL", "STRUCTURAL_BULL", "RANGE", "BEAR")


def _float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_validation_state(structural_row: Mapping[str, object] | None) -> str:
    if not structural_row:
        return "RANGE"
    regime = str(structural_row.get("structural_regime") or structural_row.get("regime") or "range").lower()
    features = structural_row.get("features") or {}
    trend = _float(features.get("trend"), 0.5)
    breadth = _float(features.get("breadth"), 0.5)

    if regime == "bear" or trend < 0.35:
        return "BEAR"
    if regime == "bull" and breadth >= 0.55:
        return "BROAD_BULL"
    if regime == "bull" or (regime == "transition" and trend >= 0.55):
        return "STRUCTURAL_BULL"
    return "RANGE"


def structural_row_for_date(
    rows: list[Mapping[str, object]],
    date_text: str,
) -> Mapping[str, object] | None:
    if not rows:
        return None
    dates = [str(row.get("date")) for row in rows]
    index = bisect_right(dates, str(date_text)) - 1
    if index < 0:
        return None
    return rows[index]


def style_opportunity_scores(score_rows: list[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = {style_id: [] for style_id in STYLE_IDS}
    for row in score_rows:
        style_id = style_for_asset_code(str(row.get("code", "")))
        if style_id is not None:
            grouped[style_id].append(row)

    result: dict[str, dict[str, object]] = {}
    for style_id, rows in grouped.items():
        ranked = sorted(rows, key=lambda item: int(item.get("rank") or 9999))
        scores = [_float(row.get("score")) for row in ranked]
        result[style_id] = {
            "asset_count": len(ranked),
            "best_score": None if not scores else round(max(scores), 4),
            "average_score": None if not scores else round(sum(scores) / len(scores), 4),
            "top_assets": [
                {
                    "code": str(row.get("code")),
                    "name": str(row.get("name")),
                    "rank": int(row.get("rank") or 0),
                    "score": round(_float(row.get("score")), 4),
                }
                for row in ranked[:3]
            ],
        }
    return result


def build_historical_style_preference(
    *,
    date_text: str,
    structural_row: Mapping[str, object] | None,
    score_rows: list[Mapping[str, object]],
) -> dict[str, object]:
    validation_state = classify_validation_state(structural_row)
    features = (structural_row or {}).get("features") or {}
    trend = _float(features.get("trend"), 0.5)
    breadth = _float(features.get("breadth"), 0.5)
    liquidity = _float(features.get("liquidity"), 0.5)
    volatility = _float(features.get("volatility"), 0.5)
    opportunity = style_opportunity_scores(score_rows)

    scores = {style_id: 50.0 for style_id in STYLE_IDS}
    reasons: dict[str, list[str]] = {style_id: [] for style_id in STYLE_IDS}

    def add(style_id: str, amount: float, reason: str) -> None:
        scores[style_id] += float(amount)
        reasons[style_id].append(reason)

    if validation_state == "BROAD_BULL":
        add("growth", 8, "BROAD_BULL: 宽基牛市支持成长进攻。")
        add("small_cap", 8, "BROAD_BULL: 宽基牛市支持中小盘扩散。")
        add("value", 5, "BROAD_BULL: 大盘价值保留核心 Beta。")
        add("dividend", -6, "BROAD_BULL: 降低纯防守偏好。")
    elif validation_state == "STRUCTURAL_BULL":
        add("growth", 12, "STRUCTURAL_BULL: 结构性牛市优先观察成长/科技主线。")
        add("small_cap", 4, "STRUCTURAL_BULL: 中小盘作为轮动扩散观察。")
        add("dividend", -4, "STRUCTURAL_BULL: 防守风格不是主导线索。")
    elif validation_state == "BEAR":
        add("dividend", 14, "BEAR: 红利低波优先作为防守风格。")
        add("value", 8, "BEAR: 大盘价值优先于高弹性风格。")
        add("growth", -12, "BEAR: 降低成长进攻偏好。")
        add("small_cap", -10, "BEAR: 降低中小盘弹性偏好。")
    else:
        add("value", 6, "RANGE: 震荡阶段偏向大盘核心。")
        add("dividend", 6, "RANGE: 震荡阶段保留红利低波防守。")
        add("growth", -4, "RANGE: 降低成长追高偏好。")
        add("small_cap", -4, "RANGE: 降低中小盘追涨偏好。")

    add("growth", (trend - 0.5) * 20 + (liquidity - 0.5) * 8, "趋势和流动性调整成长偏好。")
    add("small_cap", (breadth - 0.5) * 18 + (liquidity - 0.5) * 8, "宽度和流动性调整中小盘偏好。")
    add("value", (trend - 0.5) * 8 + (0.5 - breadth) * 5, "趋势和宽度分化调整价值偏好。")
    add("dividend", (0.5 - breadth) * 10 + (0.5 - volatility) * 8, "宽度不足和波动压力调整红利偏好。")

    for style_id in STYLE_IDS:
        best_score = opportunity.get(style_id, {}).get("best_score")
        if best_score is None:
            continue
        adjustment = max(-8.0, min(8.0, (_float(best_score) - 50.0) * 0.25))
        add(style_id, adjustment, f"机会分调整：该风格最佳机会分 {best_score}。")

    clipped = {style_id: round(max(0.0, min(100.0, value)), 4) for style_id, value in scores.items()}
    signal_share = normalize_signal_share(clipped)
    dominant = max(STYLE_IDS, key=lambda style_id: clipped[style_id])
    return {
        "date": str(date_text),
        "validation_state": validation_state,
        "style_scores": clipped,
        "relative_signal_share": signal_share,
        "dominant_style": dominant,
        "style_opportunity": opportunity,
        "evidence": reasons,
        "inputs": {
            "structural_regime": None if structural_row is None else structural_row.get("structural_regime"),
            "raw_regime": None if structural_row is None else structural_row.get("regime"),
            "features": {
                "trend": round(trend, 6),
                "breadth": round(breadth, 6),
                "liquidity": round(liquidity, 6),
                "volatility": round(volatility, 6),
            },
        },
    }


def style_pool_codes(score_rows: list[Mapping[str, object]], style_id: str, top_n: int = 3) -> list[str]:
    rows = [
        row for row in score_rows
        if style_for_asset_code(str(row.get("code", ""))) == style_id
    ]
    ranked = sorted(rows, key=lambda item: int(item.get("rank") or 9999))
    return [str(row.get("code")) for row in ranked[:top_n]]


def baseline_top_codes(score_rows: list[Mapping[str, object]], top_n: int = 3) -> list[str]:
    ranked = sorted(score_rows, key=lambda item: int(item.get("rank") or 9999))
    return [str(row.get("code")) for row in ranked[:top_n]]
