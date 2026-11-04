from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from style_allocation.style_exposure_engine import extract_style_allocation_inputs
from style_allocation.style_schema import STYLE_IDS, normalize_signal_share, style_universe_payload


DEFAULT_OUTPUT_PATH = DATA_DIR / "style_allocation_snapshot.json"


def _clip_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _add(scores: dict[str, float], style_id: str, amount: float, evidence: dict[str, list[str]], reason: str) -> None:
    if style_id not in scores:
        return
    scores[style_id] += float(amount)
    evidence[style_id].append(reason)


def _style_direction(score: float) -> str:
    if score >= 70:
        return "strong_preference"
    if score >= 58:
        return "positive_preference"
    if score >= 45:
        return "neutral_watch"
    return "low_preference"


def _opportunity_adjustment(score: object) -> float:
    if score is None:
        return 0.0
    return max(-10.0, min(10.0, (float(score) - 50.0) * 0.35))


def build_style_preference(
    inputs: Mapping[str, object],
) -> dict[str, object]:
    scores = {style_id: 50.0 for style_id in STYLE_IDS}
    evidence: dict[str, list[str]] = {style_id: [] for style_id in STYLE_IDS}
    global_reasons: list[str] = []

    macro = inputs.get("macro") or {}
    structural = inputs.get("structural") or {}
    market = inputs.get("market_structure") or {}
    industry = inputs.get("industry_opportunity") or {}
    theme_risk = inputs.get("theme_risk") or {}
    opportunity = inputs.get("asset_opportunity_by_style") or {}
    alpha_exposure = inputs.get("latest_alpha_style_exposure") or {}
    residual = inputs.get("residual_alpha") or {}

    macro_state = str(macro.get("state") or "UNKNOWN")
    structural_state = str(structural.get("state") or "UNKNOWN")
    market_state = str(market.get("state") or "UNKNOWN")
    theme_risk_level = str(theme_risk.get("level") or "unknown")
    warnings = {str(item) for item in theme_risk.get("warnings") or []}

    if macro_state == "RECOVERY":
        _add(scores, "growth", 8, evidence, "宏观 RECOVERY：信用/经济修复阶段偏向进攻风格。")
        _add(scores, "small_cap", 6, evidence, "宏观 RECOVERY：风险偏好修复有利中小盘。")
        _add(scores, "value", 4, evidence, "宏观 RECOVERY：核心宽基仍保留基础偏好。")
        global_reasons.append("MACRO_RECOVERY")
    elif macro_state in {"OVERHEAT", "STAGFLATION"}:
        _add(scores, "dividend", 10, evidence, f"宏观 {macro_state}：提高防守风格观察权重。")
        _add(scores, "value", 6, evidence, f"宏观 {macro_state}：大盘价值相对成长更稳。")
        _add(scores, "growth", -8, evidence, f"宏观 {macro_state}：压低高弹性成长偏好。")
        global_reasons.append(f"MACRO_{macro_state}")
    elif macro_state in {"CONTRACTION", "BEAR"}:
        _add(scores, "dividend", 14, evidence, f"宏观 {macro_state}：偏向红利低波防守。")
        _add(scores, "value", 8, evidence, f"宏观 {macro_state}：偏向大盘核心资产。")
        _add(scores, "growth", -10, evidence, f"宏观 {macro_state}：降低成长进攻偏好。")
        _add(scores, "small_cap", -10, evidence, f"宏观 {macro_state}：降低中小盘进攻偏好。")
        global_reasons.append(f"MACRO_{macro_state}")

    if structural_state == "STRUCTURAL_BULL_ROTATION":
        _add(scores, "growth", 12, evidence, "结构性牛市主线轮动：优先观察成长/科技主线。")
        _add(scores, "small_cap", 6, evidence, "结构性牛市主线轮动：中小盘可作为轮动扩散观察。")
        _add(scores, "dividend", -6, evidence, "结构性牛市主线轮动：降低纯防守风格偏好。")
        global_reasons.append("STRUCTURAL_BULL_ROTATION")
    elif structural_state == "BROAD_BULL":
        _add(scores, "growth", 8, evidence, "宽基牛市：成长进攻风格受益。")
        _add(scores, "small_cap", 8, evidence, "宽基牛市：中小盘扩散弹性提高。")
        _add(scores, "value", 5, evidence, "宽基牛市：大盘价值保持核心 Beta。")
        global_reasons.append("BROAD_BULL")
    elif structural_state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        _add(scores, "dividend", 16, evidence, "弱市/熊市结构：红利低波优先承担防守观察。")
        _add(scores, "value", 8, evidence, "弱市/熊市结构：大盘价值优先于高弹性风格。")
        _add(scores, "growth", -12, evidence, "弱市/熊市结构：降低成长偏好。")
        _add(scores, "small_cap", -12, evidence, "弱市/熊市结构：降低中小盘偏好。")
        global_reasons.append(structural_state)

    breadth = float(market.get("breadth") or 0.0)
    index_trend = float(market.get("index_trend") or 0.0)
    liquidity = float(market.get("liquidity") or 0.0)
    if market_state == "BULL_DIVERGENCE":
        _add(scores, "growth", 5, evidence, "市场结构 BULL_DIVERGENCE：宽基分化时更偏主线成长。")
        _add(scores, "small_cap", -4, evidence, "市场宽度偏低：中小盘扩散仍需等待确认。")
        global_reasons.append("BULL_DIVERGENCE")
    if breadth < 25:
        _add(scores, "dividend", 4, evidence, "市场宽度低于 25：保留防守风格观察。")
        _add(scores, "small_cap", -5, evidence, "市场宽度低于 25：中小盘整体扩散不足。")
    if index_trend >= 70:
        _add(scores, "growth", 4, evidence, "指数趋势分较高：支持进攻风格继续观察。")
        _add(scores, "small_cap", 3, evidence, "指数趋势分较高：支持弹性风格观察。")
    if liquidity < 50:
        _add(scores, "dividend", 3, evidence, "流动性未明显扩张：防守风格保留底仓观察价值。")
        _add(scores, "growth", -3, evidence, "流动性未明显扩张：成长风格需防高位波动。")

    theme_persistence = float(industry.get("theme_persistence") or 0.0)
    rotation_health = float(industry.get("rotation_health") or 0.0)
    top_industry_ratio = float(industry.get("top_industry_ratio") or 0.0)
    if theme_persistence >= 70:
        _add(scores, "growth", 10, evidence, "主线持续性高：成长/科技主线仍是主要观察对象。")
        global_reasons.append("THEME_PERSISTENCE_HIGH")
    if rotation_health >= 50:
        _add(scores, "small_cap", 4, evidence, "轮动健康度尚可：中小盘扩散可继续跟踪。")
    if top_industry_ratio >= 0.2:
        _add(scores, "growth", 4, evidence, "头部行业贡献较高：主线型成长风格占优。")

    if theme_risk_level in {"medium", "high"}:
        _add(scores, "growth", -8 if theme_risk_level == "medium" else -14, evidence, f"主题风险 {theme_risk_level}：成长主线需扣除拥挤/高位风险。")
        _add(scores, "small_cap", -3 if theme_risk_level == "medium" else -6, evidence, f"主题风险 {theme_risk_level}：弹性风格风险溢价下降。")
        _add(scores, "dividend", 6 if theme_risk_level == "medium" else 10, evidence, f"主题风险 {theme_risk_level}：提高防守风格观察优先级。")
        _add(scores, "value", 3 if theme_risk_level == "medium" else 6, evidence, f"主题风险 {theme_risk_level}：提高核心大盘过渡价值。")
        global_reasons.append(f"THEME_RISK_{theme_risk_level.upper()}")
    if warnings & {"high_60d_momentum_extension", "near_252d_high_position", "top_theme_price_extension_high"}:
        _add(scores, "growth", -5, evidence, "主线高位/涨幅扩张警告：成长风格不应被解释为无风险偏好。")
        _add(scores, "dividend", 4, evidence, "主线高位/涨幅扩张警告：防守风格用于风险对照。")

    for style_id in STYLE_IDS:
        style_opportunity = opportunity.get(style_id) or {}
        adjustment = _opportunity_adjustment(style_opportunity.get("best_score"))
        if adjustment:
            _add(scores, style_id, adjustment, evidence, f"资产机会分映射：该风格最佳机会分 {style_opportunity.get('best_score')}。")

    latest_alpha_dominant = None
    if alpha_exposure:
        latest_alpha_dominant = max(alpha_exposure.items(), key=lambda item: float(item[1]))
        dominant_style, dominant_share = latest_alpha_dominant
        if float(dominant_share) >= 0.67:
            _add(scores, dominant_style, 5, evidence, f"V3 最新持仓暴露 {dominant_style}={dominant_share:.1%}，说明该风格是当前系统实际关注点。")
            global_reasons.append(f"LATEST_ALPHA_EXPOSURE_{dominant_style.upper()}")

    if residual.get("economic_strength") == "weak_or_inconclusive":
        global_reasons.append("RESIDUAL_ALPHA_WEAK")

    clipped_scores = {style_id: round(_clip_score(value), 4) for style_id, value in scores.items()}
    signal_share = normalize_signal_share(clipped_scores)
    ranked = sorted(STYLE_IDS, key=lambda style_id: clipped_scores[style_id], reverse=True)
    style_environment = {
        style_id: {
            "preference_score": clipped_scores[style_id],
            "relative_signal_share": signal_share[style_id],
            "direction": _style_direction(clipped_scores[style_id]),
            "evidence": evidence[style_id],
            "opportunity": (opportunity.get(style_id) or {}),
            "latest_alpha_exposure": round(float(alpha_exposure.get(style_id, 0.0)), 6),
        }
        for style_id in STYLE_IDS
    }

    confidence = 0.55
    confidence += min(0.15, float(macro.get("confidence") or 0.0) * 0.05)
    confidence += min(0.15, float(structural.get("confidence") or 0.0) * 0.08)
    if residual.get("economic_strength") == "weak_or_inconclusive":
        confidence -= 0.08
    if theme_risk_level == "high":
        confidence -= 0.05
    confidence = round(max(0.0, min(0.95, confidence)), 4)

    return {
        "style_environment": style_environment,
        "dominant_style": ranked[0],
        "top_styles": [
            {
                "style": style_id,
                "preference_score": clipped_scores[style_id],
                "relative_signal_share": signal_share[style_id],
                "direction": style_environment[style_id]["direction"],
            }
            for style_id in ranked
        ],
        "confidence": confidence,
        "reason_codes": global_reasons,
        "interpretation": (
            "This is a non-investable style preference layer. It explains which style beta the system should study under the current macro/structure context, "
            "but it is not an ETF weight, position size, trade signal, or backtest result."
        ),
    }


def build_style_allocation_snapshot(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    inputs = extract_style_allocation_inputs(data_dir)
    preference = build_style_preference(inputs)
    return {
        "metadata": {
            "engine": "V3.5.1 Style Allocation Engine Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": inputs.get("as_of"),
            "purpose": "Map macro, structural, theme-risk and alpha-style evidence into style preference only.",
            "not_an_etf_weight_model": True,
        },
        "style_universe": style_universe_payload(),
        "inputs": inputs,
        "preference": preference,
        "constraints": {
            "analysis_only": True,
            "style_preference_only": True,
            "no_asset_weight": True,
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
            "no_best_style_selection_for_trading": True,
            "alpha_model_unchanged": True,
            "router_unchanged": True,
        },
    }


def write_style_allocation_snapshot(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
