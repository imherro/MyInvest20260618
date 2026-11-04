from __future__ import annotations

from typing import Mapping


ETF_UNIVERSE: list[dict[str, object]] = [
    {
        "code": "510300.SH",
        "name": "沪深300ETF",
        "bucket": "broad_base",
        "risk_tier": "moderate",
        "styles": {"value": 0.35, "growth": 0.25, "low_vol": 0.15},
        "eligible_regimes": ["bull", "range", "transition"],
    },
    {
        "code": "510880.SH",
        "name": "红利ETF",
        "bucket": "dividend",
        "risk_tier": "defensive",
        "styles": {"dividend": 0.80, "low_vol": 0.25, "value": 0.20},
        "eligible_regimes": ["range", "bear", "transition"],
    },
    {
        "code": "510500.SH",
        "name": "中证500ETF",
        "bucket": "broad_mid_cap",
        "risk_tier": "moderate",
        "styles": {"small_cap": 0.45, "value": 0.25, "growth": 0.20},
        "eligible_regimes": ["bull", "range"],
    },
    {
        "code": "159915.SZ",
        "name": "创业板ETF",
        "bucket": "growth",
        "risk_tier": "aggressive",
        "styles": {"growth": 0.75, "small_cap": 0.25},
        "eligible_regimes": ["bull"],
    },
    {
        "code": "511880.SH",
        "name": "银华日利ETF",
        "bucket": "cash_proxy",
        "risk_tier": "cash_defensive",
        "styles": {"cash_proxy": 0.95, "low_vol": 0.20},
        "eligible_regimes": ["bear", "transition", "range"],
    },
]


def _style_score(style_scores: Mapping[str, object], style: str) -> float:
    return max(0.0, min(1.0, float(style_scores.get(style, 0.0))))


def _regime_penalty(regime: str, eligible_regimes: list[str]) -> float:
    return 1.0 if regime in eligible_regimes else 0.82


def _risk_tier_adjustment(risk_score: float, risk_tier: str) -> float:
    if risk_tier == "aggressive":
        return 1.0 - 0.28 * risk_score
    if risk_tier == "cash_defensive":
        return 0.82 + 0.24 * risk_score
    if risk_tier == "defensive":
        return 0.92 + 0.12 * risk_score
    return 1.0 - 0.08 * risk_score


def _candidate_score(
    etf: Mapping[str, object],
    style_scores: Mapping[str, object],
    *,
    regime: str,
    risk_score: float,
) -> float:
    style_weights = etf.get("styles")
    if not isinstance(style_weights, Mapping) or not style_weights:
        return 0.0
    weighted_sum = sum(_style_score(style_scores, style) * float(weight) for style, weight in style_weights.items())
    weight_total = sum(float(weight) for weight in style_weights.values())
    if weight_total <= 0:
        return 0.0

    eligible = [str(item) for item in etf.get("eligible_regimes", [])]
    base_score = weighted_sum / weight_total
    adjusted = base_score * _regime_penalty(regime, eligible) * _risk_tier_adjustment(risk_score, str(etf["risk_tier"]))
    return round(max(0.0, min(1.0, adjusted)), 6)


def _primary_style(etf: Mapping[str, object]) -> str:
    style_weights = etf.get("styles")
    if not isinstance(style_weights, Mapping) or not style_weights:
        return "unknown"
    return max(style_weights.items(), key=lambda item: float(item[1]))[0]


def _candidate_record(
    etf: Mapping[str, object],
    score: float,
    *,
    regime: str,
) -> dict[str, object]:
    eligible = [str(item) for item in etf.get("eligible_regimes", [])]
    return {
        "code": etf["code"],
        "name": etf["name"],
        "bucket": etf["bucket"],
        "primary_style": _primary_style(etf),
        "risk_tier": etf["risk_tier"],
        "eligible_regimes": eligible,
        "regime_eligible": regime in eligible,
        "candidate_score": score,
        "style_weights": etf["styles"],
    }


def _style_universe(candidates: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for candidate in candidates:
        style = str(candidate["primary_style"])
        grouped.setdefault(style, []).append(
            {
                "code": candidate["code"],
                "name": candidate["name"],
                "candidate_score": candidate["candidate_score"],
            }
        )
    return grouped


def build_etf_universe(style_factor_snapshot: Mapping[str, object]) -> dict[str, object]:
    style_scores = style_factor_snapshot.get("style_scores")
    if not isinstance(style_scores, Mapping):
        raise ValueError("style_factor_snapshot missing style_scores")
    regime = str(style_factor_snapshot.get("regime", "range"))
    risk_score = max(0.0, min(1.0, float(style_factor_snapshot.get("risk_score", 0.5))))

    candidates = [
        _candidate_record(etf, _candidate_score(etf, style_scores, regime=regime, risk_score=risk_score), regime=regime)
        for etf in ETF_UNIVERSE
    ]
    candidates = sorted(candidates, key=lambda item: float(item["candidate_score"]), reverse=True)
    return {
        "engine": "ETF Universe Builder A1.1",
        "as_of": style_factor_snapshot.get("as_of"),
        "regime": regime,
        "risk_score": round(risk_score, 6),
        "candidate_count": len(candidates),
        "top_candidates": candidates[:6],
        "candidates": candidates,
        "style_universe": _style_universe(candidates),
        "constraints": {
            "etf_only": True,
            "no_single_stock_selection": True,
            "no_trade_execution": True,
            "universe_generation_only": True,
        },
    }
