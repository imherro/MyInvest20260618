from __future__ import annotations

from statistics import mean, median
from typing import Mapping

import pandas as pd

from core.etf_return_utils import coerce_price_frame, compound_recent_return, daily_return_series
from core.risk_score_engine import _clip


RETURN_WINDOWS = (20, 60)
STYLE_KEYS = ("growth", "value", "low_vol", "dividend", "small_cap", "cash_proxy")


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _coerce_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return coerce_price_frame(frame)


def _window_return(frame: pd.DataFrame, window: int) -> float | None:
    return compound_recent_return(frame, window)


def _recent_volatility(frame: pd.DataFrame, window: int = 60) -> float | None:
    returns = daily_return_series(frame).dropna().tail(window)
    if len(returns) < max(10, window // 3):
        return None
    return float(returns.std() * (252 ** 0.5))


def _recent_drawdown(frame: pd.DataFrame, window: int = 60) -> float | None:
    returns = daily_return_series(frame).dropna().tail(window)
    if len(returns) < 10:
        return None
    equity = (1.0 + returns).cumprod()
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    return float(drawdown.min())


def _return_quality(return_20: float | None, return_60: float | None, volatility: float | None) -> float:
    momentum = 0.0
    if return_20 is not None:
        momentum += 0.45 * _clip((return_20 + 0.08) / 0.18)
    if return_60 is not None:
        momentum += 0.55 * _clip((return_60 + 0.12) / 0.28)
    if return_20 is None and return_60 is None:
        momentum = 0.5

    vol_penalty = 0.0 if volatility is None else 0.18 * _clip((volatility - 0.18) / 0.35)
    return _clip(momentum - vol_penalty)


def _price_metrics(price_history: Mapping[str, pd.DataFrame]) -> dict[str, dict[str, object]]:
    metrics: dict[str, dict[str, object]] = {}
    for code, raw_frame in price_history.items():
        frame = _coerce_price_frame(raw_frame)
        if frame.empty:
            continue
        return_20 = _window_return(frame, 20)
        return_60 = _window_return(frame, 60)
        volatility = _recent_volatility(frame)
        drawdown = _recent_drawdown(frame)
        metrics[code] = {
            "latest_date": str(frame["trade_date"].iloc[-1]),
            "latest_close": _round(float(frame["close"].iloc[-1]), 4),
            "sessions": int(len(frame)),
            "return_20": _round(return_20),
            "return_60": _round(return_60),
            "volatility_60": _round(volatility),
            "max_drawdown_60": _round(drawdown),
            "return_quality": _round(_return_quality(return_20, return_60, volatility)),
        }
    return metrics


def _percentile_scores(values: Mapping[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ranked = sorted(values.items(), key=lambda item: item[1])
    if len(ranked) == 1:
        return {ranked[0][0]: 0.5}
    scores: dict[str, float] = {}
    denominator = len(ranked) - 1
    for index, (code, _value) in enumerate(ranked):
        scores[code] = round(index / denominator, 6)
    return scores


def _ranking_stability(price_history: Mapping[str, pd.DataFrame], codes: list[str], window: int = 20) -> dict[str, float]:
    daily_returns = {}
    for code in codes:
        frame = _coerce_price_frame(price_history.get(code, pd.DataFrame()))
        if len(frame) > window:
            daily_returns[code] = daily_return_series(frame)
    if len(daily_returns) < 2:
        return {code: 0.5 for code in codes}

    returns_matrix = pd.DataFrame(daily_returns).sort_index().dropna(how="all").fillna(0.0)
    rolling_returns = (1.0 + returns_matrix).rolling(window=window).apply(lambda values: float(values.prod() - 1.0), raw=True)
    rolling_returns = rolling_returns.tail(window).dropna(how="all")
    if rolling_returns.empty:
        return {code: 0.5 for code in codes}

    rank_matrix = rolling_returns.rank(axis=1, ascending=False, pct=True)
    stability: dict[str, float] = {}
    for code in codes:
        if code not in rank_matrix:
            stability[code] = 0.5
            continue
        series = rank_matrix[code].dropna()
        if series.empty:
            stability[code] = 0.5
            continue
        stability[code] = round(_clip(1.0 - float(series.mean())), 6)
    return stability


def _candidate_lookup(etf_universe: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    candidates = etf_universe.get("candidates", [])
    if not isinstance(candidates, list):
        return {}
    return {str(item["code"]): item for item in candidates if isinstance(item, Mapping) and "code" in item}


def _style_signal_scores(
    style_scores: Mapping[str, object],
    scored_candidates: list[dict[str, object]],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for style in STYLE_KEYS:
        style_base = _clip(float(style_scores.get(style, 0.0)))
        members = [item for item in scored_candidates if item["primary_style"] == style]
        eligible_members = [item for item in members if item.get("regime_eligible") is True]
        signal_members = eligible_members or members
        if signal_members:
            relative = mean(float(item["relative_strength_score"]) for item in signal_members)
            stability = mean(float(item["ranking_stability"]) for item in signal_members)
            signal = mean(float(item["signal_score"]) for item in signal_members)
            eligibility_adjustment = 1.0 if eligible_members else 0.65
        else:
            relative = 0.5
            stability = 0.5
            signal = 0.5
            eligibility_adjustment = 1.0
        result[style] = round(
            _clip((0.40 * style_base + 0.20 * relative + 0.15 * stability + 0.25 * signal) * eligibility_adjustment),
            6,
        )
    return result


def _target_weights(scored_candidates: list[dict[str, object]], limit: int = 4) -> dict[str, float]:
    eligible = [item for item in scored_candidates if item.get("regime_eligible") is True]
    selected = (eligible or scored_candidates)[:limit]
    score_sum = sum(max(0.0, float(item["signal_score"])) for item in selected)
    if score_sum <= 0:
        return {}
    return {
        str(item["code"]): round(max(0.0, float(item["signal_score"])) / score_sum, 6)
        for item in selected
    }


def _rebalance_signal(top_styles: list[dict[str, object]], confidence: float, target_weights: Mapping[str, float]) -> str:
    if not target_weights:
        return "insufficient_data"
    if confidence < 0.45:
        return "hold_universe"
    if not top_styles:
        return "hold_universe"
    return f"rotate_to_{top_styles[0]['style']}"


def _confidence(
    scored_candidates: list[dict[str, object]],
    candidate_count: int,
    target_weights: Mapping[str, float],
) -> dict[str, object]:
    if not scored_candidates or candidate_count <= 0:
        return {
            "score": 0.0,
            "level": "insufficient",
            "reason": "ETF 历史价格样本不足，无法计算轮动信号。",
        }

    coverage = _clip(len(scored_candidates) / candidate_count)
    stability = mean(float(item["ranking_stability"]) for item in scored_candidates[: min(4, len(scored_candidates))])
    scores = [float(item["signal_score"]) for item in scored_candidates]
    spread = scores[0] - median(scores)
    concentration = _clip(spread / 0.25)
    weight_count = len(target_weights)
    diversification = _clip(weight_count / 4)
    score = round(_clip(0.35 * coverage + 0.25 * stability + 0.25 * concentration + 0.15 * diversification), 6)
    if score >= 0.7:
        level = "high"
    elif score >= 0.55:
        level = "medium"
    elif score >= 0.4:
        level = "low"
    else:
        level = "insufficient"
    return {
        "score": score,
        "level": level,
        "reason": (
            f"覆盖 {len(scored_candidates)}/{candidate_count} 个 ETF，"
            f"Top 组合稳定度 {stability:.2f}，分数集中度 {concentration:.2f}。"
        ),
    }


def build_etf_rotation_signal(
    style_factor_snapshot: Mapping[str, object],
    etf_universe: Mapping[str, object],
    price_history: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    candidates = _candidate_lookup(etf_universe)
    metrics = _price_metrics(price_history)
    relative_scores = _percentile_scores(
        {
            code: float(payload["return_quality"])
            for code, payload in metrics.items()
            if payload.get("return_quality") is not None
        }
    )
    stability_scores = _ranking_stability(price_history, list(candidates))

    scored_candidates: list[dict[str, object]] = []
    for code, candidate in candidates.items():
        if code not in metrics:
            continue
        candidate_score = _clip(float(candidate.get("candidate_score", 0.0)))
        relative_strength = relative_scores.get(code, 0.5)
        stability = stability_scores.get(code, 0.5)
        return_quality = float(metrics[code].get("return_quality", 0.5) or 0.5)
        regime_eligible = bool(candidate.get("regime_eligible", False))
        regime_condition_adjustment = 1.0 if regime_eligible else 0.65
        signal_score = _clip(
            0.35 * candidate_score
            + 0.30 * relative_strength
            + 0.20 * stability
            + 0.15 * return_quality
        ) * regime_condition_adjustment
        scored_candidates.append(
            {
                "code": code,
                "name": candidate.get("name"),
                "primary_style": candidate.get("primary_style"),
                "risk_tier": candidate.get("risk_tier"),
                "regime_eligible": regime_eligible,
                "regime_condition_adjustment": round(regime_condition_adjustment, 6),
                "candidate_score": round(candidate_score, 6),
                "relative_strength_score": round(relative_strength, 6),
                "ranking_stability": round(stability, 6),
                "return_quality": round(return_quality, 6),
                "signal_score": round(signal_score, 6),
                "price_metrics": metrics[code],
            }
        )

    scored_candidates.sort(key=lambda item: float(item["signal_score"]), reverse=True)
    target_weights = _target_weights(scored_candidates)
    confidence = _confidence(scored_candidates, int(etf_universe.get("candidate_count", len(candidates))), target_weights)
    style_signal_scores = _style_signal_scores(
        style_factor_snapshot.get("style_scores", {}),
        scored_candidates,
    )

    top_styles = sorted(style_signal_scores.items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "engine": "ETF Rotation Signal Engine A1.2",
        "as_of": style_factor_snapshot.get("as_of"),
        "regime": style_factor_snapshot.get("regime"),
        "top_styles": [style for style, _score_value in top_styles],
        "style_signal_score": style_signal_scores,
        "top_candidates": scored_candidates[:6],
        "etf_target_weights": target_weights,
        "rebalance_signal": _rebalance_signal(
            [{"style": style, "score": score} for style, score in top_styles],
            float(confidence["score"]),
            target_weights,
        ),
        "confidence": confidence,
        "data_coverage": {
            "candidate_count": int(etf_universe.get("candidate_count", len(candidates))),
            "priced_candidates": len(scored_candidates),
            "missing_price_candidates": sorted(set(candidates) - set(metrics)),
        },
        "constraints": {
            "etf_level_signal_only": True,
            "target_weights_are_simulation_inputs": True,
            "no_single_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
        },
        "method": {
            "signal_score": "A1.1 candidate score + ETF relative strength + ranking stability + return quality, with regime-ineligible candidates discounted.",
            "relative_strength": "Percentile ranking of recent 20/60-session return quality among ETF candidates.",
            "ranking_stability": "Recent persistence of ETF ranking within the candidate set.",
        },
    }
