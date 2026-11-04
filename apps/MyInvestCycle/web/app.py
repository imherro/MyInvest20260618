from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from statistics import mean

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BREADTH_HISTORY_SAMPLE_SIZE, DATA_DIR, DEFAULT_INDEX_CODE, WEB_PORT
from core.breadth import get_market_daily, get_market_history_sample
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import get_index_daily, normalize_trade_date
from core.etf_rotation_signal_engine import build_etf_rotation_signal
from core.exposure_controller import build_exposure_decision
from core.features import build_feature_frame
from core.liquidity import get_moneyflow_hsgt
from core.capital_controller import load_portfolio_policy
from core.execution_policy import load_execution_policy
from core.execution_simulator import simulate_execution_layer
from core.etf_universe_builder import build_etf_universe
from core.meta_signal_engine import build_meta_edge_signal, load_meta_edge_rules
from core.portfolio_allocator import build_portfolio_allocation
from core.regime_adapter import adapt_regime_payload
from core.risk_score_engine import load_risk_policy
from core.style_factor_engine import build_style_factor_snapshot
from core.strategy_filter import load_strategy_policy
from core.strategy_router import build_strategy_route
from engine.cycle_detector import detect_current_cycle_track, detect_major_cycles
from engine.market_engine import analyze_index_regime
from engine.regime_explainer import explain_regime
from macro.data_quality import audit_macro_records
from macro.indicator_registry import registry_as_dict
from macro.macro_cycle_engine import build_macro_cycle_snapshot
from macro.macro_loader import DEFAULT_MACRO_INDICATORS, load_macro_indicators
from market_structure.structure_engine import build_structure_snapshot
from industry_structure.opportunity_engine import build_industry_opportunity_snapshot
from structural_bull.structural_bull_engine import build_structural_bull_snapshot
from theme_risk.opportunity_quality_engine import build_theme_risk_snapshot
from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot
from adaptive_allocation.decision_trace import build_allocation_trace_snapshot


app = FastAPI(title="MyInvestCycle Regime API", version="0.8")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "web" / "static"), name="static")


@app.middleware("http")
async def no_store_api_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _today_text() -> str:
    return date.today().strftime("%Y%m%d")


def _load_index_window(start_date: str, end_date: str):
    df = get_index_daily(DEFAULT_INDEX_CODE, start_date, end_date)
    if df.empty:
        raise HTTPException(status_code=503, detail="No index data returned from Tushare.")
    return df


@lru_cache(maxsize=2)
def _load_cycle_index(end_date: str):
    return get_index_daily(DEFAULT_INDEX_CODE, "19940101", end_date)


def _load_hsgt_for_index(index_df, as_of: str):
    window = index_df[index_df["trade_date"] <= as_of].tail(30)
    if window.empty:
        return None
    try:
        return get_moneyflow_hsgt(str(window["trade_date"].iloc[0]), as_of)
    except Exception:
        return None


def _read_data_json(file_name: str):
    path = ROOT_DIR / "data" / file_name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


SCORE_HISTORY_KEYS = ("trend", "breadth", "liquidity", "volatility")


def _float_or_none(value, digits: int = 4):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _score_history_item(
    date_text: str,
    regime: str | None,
    structural_regime: str | None,
    features: dict[str, object],
    close: object,
) -> dict[str, object] | None:
    scores = {key: _float_or_none(features.get(key), 4) for key in SCORE_HISTORY_KEYS}
    if any(value is None for value in scores.values()):
        return None
    scores["regime_score"] = _float_or_none(features.get("regime_score"), 4)
    scores["confidence"] = _float_or_none(features.get("confidence"), 4)
    return {
        "as_of": date_text,
        "regime": regime,
        "structural_regime": structural_regime,
        "scores": scores,
        "index": {"close": _float_or_none(close, 4)},
    }


def _cached_score_history_items(
    start_date: str,
    end_date: str,
    close_by_date: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    dataset = _read_data_json("structural_survival_dataset.json")
    if not isinstance(dataset, list):
        return [], {"source": "structural_survival_dataset.json", "available": False}

    items = []
    dates = []
    for row in dataset:
        date_text = str(row.get("date") or "")
        if not date_text:
            continue
        dates.append(date_text)
        if start_date <= date_text <= end_date:
            item = _score_history_item(
                date_text,
                row.get("raw_regime"),
                row.get("structural_regime"),
                row.get("features") or {},
                close_by_date.get(date_text),
            )
            if item:
                items.append(item)

    return items, {
        "source": "structural_survival_dataset.json",
        "available": True,
        "cached_start": min(dates) if dates else None,
        "cached_end": max(dates) if dates else None,
    }


def _dynamic_score_history_items(
    target_dates: list[str],
    index_df: pd.DataFrame,
) -> list[dict[str, object]]:
    if len(target_dates) > 80:
        raise HTTPException(
            status_code=503,
            detail="score history cache is missing too many trading days; rebuild structural_survival_dataset first",
        )

    items = []
    for trade_date in target_dates:
        index_slice = index_df[index_df["trade_date"] <= trade_date]
        market_daily = get_market_daily(trade_date)
        market_history = get_market_history_sample(
            market_daily,
            _calendar_shift(trade_date, -370),
            trade_date,
            sample_size=BREADTH_HISTORY_SAMPLE_SIZE,
        )
        hsgt = _load_hsgt_for_index(index_df, trade_date)
        result = analyze_index_regime(
            index_slice,
            market_daily_df=market_daily,
            market_history_df=market_history,
            hsgt_df=hsgt,
        )
        feature_row = build_feature_frame(index_slice).iloc[-1]
        item = _score_history_item(
            str(result["as_of"]),
            result.get("regime"),
            None,
            {
                **(result.get("sub_scores") or {}),
                "regime_score": result.get("regime_score"),
                "confidence": result.get("confidence"),
            },
            feature_row["close"],
        )
        if item:
            items.append(item)
    return items


def _read_shadow_backtest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "shadow_equity_curve.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_regime_attribution_payload() -> dict[str, object] | None:
    path = DATA_DIR / "regime_performance_attribution.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_etf_rotation_backtest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "etf_rotation_backtest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_macro_style_etf_backtest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "macro_style_etf_backtest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v2_allocation_backtest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v2_allocation_backtest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v2_policy_sensitivity_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v2_policy_sensitivity.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_structural_bull_policy_payload() -> dict[str, object] | None:
    path = DATA_DIR / "structural_bull_policy_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v2_full_cycle_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v2_full_cycle_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v2_full_cycle_backtest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v2_full_cycle_backtest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_history_expansion_payload() -> dict[str, object] | None:
    path = DATA_DIR / "history_expansion_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_alpha_portfolio_risk_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "alpha_portfolio_risk_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_alpha_robustness_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "alpha_robustness_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_residual_alpha_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "residual_alpha_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_style_allocation_snapshot_payload() -> dict[str, object] | None:
    path = DATA_DIR / "style_allocation_snapshot.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_style_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "style_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_style_incremental_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "style_incremental_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_policy_snapshot_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_policy_snapshot.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_policy_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_policy_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_risk_snapshot_payload() -> dict[str, object] | None:
    path = DATA_DIR / "opportunity_risk_snapshot.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_risk_policy_payload() -> dict[str, object] | None:
    path = DATA_DIR / "opportunity_risk_policy.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_policy_effectiveness_payload() -> dict[str, object] | None:
    path = DATA_DIR / "policy_effectiveness.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_market_phase_payload() -> dict[str, object] | None:
    path = DATA_DIR / "market_phase_snapshot.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_macro_context_history_payload() -> dict[str, object] | None:
    path = DATA_DIR / "macro_context_history.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_phase_effectiveness_payload() -> dict[str, object] | None:
    path = DATA_DIR / "phase_effectiveness.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_simulation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_simulation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_effectiveness_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_effectiveness.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_context_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_context_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_balanced_context_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "balanced_context_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_balanced_candidate_failure_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "balanced_candidate_failure_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_numeric_context_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_numeric_context.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_macro_enhanced_context_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "macro_enhanced_context_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_context_state_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_context_state_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_gradient_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_gradient_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_gradient_robustness_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_gradient_robustness.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_gradient_condition_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_gradient_condition_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_gradient_candidate_rules_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_gradient_candidate_rules.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_policy_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_policy_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_decision_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_decision_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_exposure_context_score_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "exposure_context_score_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_protection_score_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "protection_score_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_two_axis_context_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "two_axis_context_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_context_information_attribution_payload() -> dict[str, object] | None:
    path = DATA_DIR / "context_information_attribution.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_research_foundation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "opportunity_research_foundation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_context_features_payload() -> dict[str, object] | None:
    path = DATA_DIR / "opportunity_context_features.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_feature_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "opportunity_feature_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_feature_attribution_payload() -> dict[str, object] | None:
    path = DATA_DIR / "opportunity_feature_attribution.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_opportunity_v7_architecture_payload() -> dict[str, object] | None:
    doc_path = ROOT_DIR / "docs" / "opportunity_research_v7_architecture.md"
    if not doc_path.exists():
        return None

    foundation = _read_opportunity_research_foundation_payload() or {}
    context_features = _read_opportunity_context_features_payload() or {}
    feature_validation = _read_opportunity_feature_validation_payload() or {}
    feature_attribution = _read_opportunity_feature_attribution_payload() or {}
    attribution_summary = feature_attribution.get("summary") if isinstance(feature_attribution, dict) else {}
    validation_summary = feature_validation.get("summary") if isinstance(feature_validation, dict) else {}
    foundation_summary = foundation.get("summary") if isinstance(foundation, dict) else {}
    context_summary = context_features.get("summary") if isinstance(context_features, dict) else {}

    source_layers = [
        {
            "version": "V7.1",
            "name": "Asset Research Foundation",
            "artifact": "data/opportunity_research_foundation.json",
            "status": "retained",
            "role": "资产池、研究代理、覆盖率和时间安全边界。",
        },
        {
            "version": "V7.2",
            "name": "Context Features",
            "artifact": "data/opportunity_context_features.json",
            "status": "retained",
            "role": "固定动量、相对强弱、趋势、风险、结构特征字段。",
        },
        {
            "version": "V7.3",
            "name": "Feature Validation",
            "artifact": "data/opportunity_feature_validation.json",
            "status": "retained",
            "role": "5/20/60 日 IC 有效性审计，proxy 与 ETF 分离。",
        },
        {
            "version": "V7.4",
            "name": "Feature Attribution",
            "artifact": "data/opportunity_feature_attribution.json",
            "status": "retained",
            "role": "保留/观察/暂弃标签和环境一致性归因。",
        },
    ]
    rejected_outputs = [
        {
            "name": "Opportunity Score",
            "status": "rejected",
            "reason": "特征稳定性不足，V7.4 结论为 feature_attribution_not_ready_for_opportunity_score。",
        },
        {"name": "Ranking", "status": "rejected", "reason": "尚无验证通过的 alpha 或机会层。"},
        {"name": "Top N", "status": "rejected", "reason": "会形成隐含资产选择，但缺少排名有效性证据。"},
        {"name": "Allocation", "status": "rejected", "reason": "尚无机会引擎，不应生成配置建议。"},
        {"name": "ETF weight", "status": "rejected", "reason": "特征归因不等于可交易 ETF 权重。"},
        {"name": "Trading", "status": "rejected", "reason": "本层为研究只读，不连接券商或下单。"},
        {"name": "New feature search", "status": "rejected", "reason": "冻结阶段继续挖特征会放大过拟合风险。"},
    ]
    return {
        "metadata": {
            "engine": "V7.5 Opportunity Research Layer Freeze & Audit Summary",
            "status": "frozen",
            "doc_path": "docs/opportunity_research_v7_architecture.md",
            "audit_script": "scripts/audit_v7_architecture_consistency.py",
            "source_layers": ["V7.1", "V7.2", "V7.3", "V7.4"],
        },
        "summary": {
            "freeze_status": "frozen",
            "retained_layer_count": len(source_layers),
            "rejected_output_count": len(rejected_outputs),
            "verified_count": 6,
            "not_verified_count": 7,
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "conclusion": (
                attribution_summary.get("conclusion")
                if isinstance(attribution_summary, dict)
                else "feature_attribution_not_ready_for_opportunity_score"
            ),
            "key_read": "V7 is frozen as a research-only architecture; it keeps the audit foundation but rejects score, ranking, allocation, ETF weights, and trading.",
        },
        "retained_layers": source_layers,
        "rejected_outputs": rejected_outputs,
        "verified": [
            "asset research foundation",
            "proxy and tradable history separation",
            "fixed feature audit framework",
            "time-safe feature construction",
            "IC-based feature effectiveness audit",
            "feature retention and regime consistency attribution",
        ],
        "not_verified": [
            "opportunity prediction",
            "asset ranking",
            "Top N asset selection",
            "allocation alpha",
            "ETF weight generation",
            "tradable strategy improvement",
            "trading signal generation",
        ],
        "evidence": {
            "asset_count": foundation_summary.get("asset_count") if isinstance(foundation_summary, dict) else None,
            "feature_groups": context_summary.get("feature_groups") if isinstance(context_summary, dict) else [],
            "feature_validation_result_count": (
                validation_summary.get("result_count") if isinstance(validation_summary, dict) else None
            ),
            "feature_attribution_count": (
                attribution_summary.get("attribution_count") if isinstance(attribution_summary, dict) else None
            ),
            "retention_counts": attribution_summary.get("retention_counts") if isinstance(attribution_summary, dict) else {},
        },
        "constraints": {
            "research_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_create_feature_weight": True,
            "does_not_rank_assets": True,
            "does_not_select_top_assets": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization_for_investable_output": True,
        },
    }


def _read_research_decision_context_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_decision_context.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_decision_scenario_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_decision_scenario_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_decision_contradiction_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_decision_contradiction.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_decision_v8_architecture_payload() -> dict[str, object] | None:
    doc_path = ROOT_DIR / "docs" / "research_decision_v8_architecture.md"
    if not doc_path.exists():
        return None

    context = _read_research_decision_context_payload() or {}
    scenario = _read_research_decision_scenario_audit_payload() or {}
    contradiction = _read_research_decision_contradiction_payload() or {}
    context_summary = context.get("summary") if isinstance(context, dict) else {}
    scenario_summary = scenario.get("summary") if isinstance(scenario, dict) else {}
    contradiction_summary = contradiction.get("summary") if isinstance(contradiction, dict) else {}
    retained_layers = [
        {
            "version": "V8.1",
            "name": "Research Decision Context",
            "artifact": "data/research_decision_context.json",
            "status": "retained",
            "role": "连接 V6 风险上下文与 V7 机会研究状态，只生成研究语境。",
        },
        {
            "version": "V8.2",
            "name": "Historical Scenario Audit",
            "artifact": "data/research_decision_scenario_audit.json",
            "status": "retained",
            "role": "固定历史场景的一致性、切换、矛盾和覆盖审计。",
        },
        {
            "version": "V8.3",
            "name": "Contradiction Attribution",
            "artifact": "data/research_decision_contradiction.json",
            "status": "retained",
            "role": "归因重点历史场景中的解释失败原因，不修改规则。",
        },
    ]
    rejected_outputs = [
        {"name": "Score", "status": "rejected", "reason": "V8 只解释研究语境，不证明预测能力。"},
        {"name": "Ranking", "status": "rejected", "reason": "V7 机会排名仍未验证。"},
        {"name": "Asset Selection", "status": "rejected", "reason": "V8 不输出资产。"},
        {"name": "Top N", "status": "rejected", "reason": "没有验证通过的排名层。"},
        {"name": "Allocation", "status": "rejected", "reason": "V8 不是配置引擎。"},
        {"name": "ETF Weight", "status": "rejected", "reason": "V8 不产生可交易权重。"},
        {"name": "Trading", "status": "rejected", "reason": "本层为研究只读。"},
        {"name": "New State", "status": "rejected", "reason": "V8.3 只解释失败，不修改状态体系。"},
        {"name": "V6/V7 Modification", "status": "rejected", "reason": "V8 只消费冻结的 V6/V7 产物。"},
    ]
    return {
        "metadata": {
            "engine": "V8.4 Research Decision Architecture Freeze & Summary",
            "status": "frozen",
            "doc_path": "docs/research_decision_v8_architecture.md",
            "audit_script": "scripts/audit_v8_architecture_consistency.py",
            "source_layers": ["V8.1", "V8.2", "V8.3"],
        },
        "summary": {
            "freeze_status": "frozen",
            "retained_layer_count": len(retained_layers),
            "rejected_output_count": len(rejected_outputs),
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "conclusion": "v8_research_interpretation_frozen_no_strategy",
            "key_read": "V8 is frozen as a research interpretation layer; it does not create score, ranking, asset selection, allocation, ETF weights, or trades.",
        },
        "retained_layers": retained_layers,
        "rejected_outputs": rejected_outputs,
        "evidence": {
            "v8_1_decision_context": (
                context_summary.get("decision_context") if isinstance(context_summary, dict) else None
            ),
            "v8_1_research_posture": (
                context_summary.get("research_posture") if isinstance(context_summary, dict) else None
            ),
            "v8_2_scenario_count": (
                scenario_summary.get("scenario_count") if isinstance(scenario_summary, dict) else None
            ),
            "v8_2_consistency_counts": (
                scenario_summary.get("consistency_counts") if isinstance(scenario_summary, dict) else {}
            ),
            "v8_3_focus_scenario_count": (
                contradiction_summary.get("focus_scenario_count") if isinstance(contradiction_summary, dict) else None
            ),
            "v8_3_attribution_count": (
                contradiction_summary.get("attribution_count") if isinstance(contradiction_summary, dict) else None
            ),
            "v8_3_contradiction_type_counts": (
                contradiction_summary.get("contradiction_type_counts") if isinstance(contradiction_summary, dict) else {}
            ),
        },
        "constraints": {
            "research_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_rank_assets": True,
            "does_not_select_top_assets": True,
            "does_not_generate_position": True,
            "does_not_modify_v6": True,
            "does_not_modify_v7": True,
            "does_not_add_state": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization_for_investable_output": True,
        },
    }


def _read_allocation_research_architecture_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_research_architecture.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_research_evidence_freeze_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_research_evidence_freeze.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_research_execution_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_research_execution_runs.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_research_result_review_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_research_result_review.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_research_final_boundary_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_research_final_boundary.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_external_validation_protocol_payload() -> dict[str, object] | None:
    path = DATA_DIR / "external_validation_protocol.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_h2_external_validation_execution_payload() -> dict[str, object] | None:
    path = DATA_DIR / "h2_external_validation_execution.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_h2_external_validation_result_freeze_payload() -> dict[str, object] | None:
    path = DATA_DIR / "h2_external_validation_result_freeze.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_phase_closure_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_phase_closure.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_to_implementation_boundary_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_to_implementation_boundary.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_implementation_readiness_evidence_specification_payload() -> dict[str, object] | None:
    path = DATA_DIR / "implementation_readiness_evidence_specification.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_implementation_readiness_evidence_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "implementation_readiness_evidence_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_component_evidence_submission_protocol_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_component_evidence_submission_protocol.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_evidence_package_validation_engine_payload() -> dict[str, object] | None:
    path = DATA_DIR / "evidence_package_validation_engine.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_invalid_evidence_package_rejection_example_payload() -> dict[str, object] | None:
    path = DATA_DIR / "invalid_evidence_package_rejection_example.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_implementation_readiness_governance_freeze_payload() -> dict[str, object] | None:
    path = DATA_DIR / "implementation_readiness_governance_freeze.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_evidence_package_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_evidence_package.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_framework_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_observation_framework.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_observation_log_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_observation_log.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_observation_review_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_observation_review.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_manual_event_capture_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_manual_event_capture.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_event_quality_audit_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_event_quality_audit.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_first_event_workflow_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_first_event_workflow.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_event_input_package_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_event_input_package.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_risk_diagnostic_shadow_evidence_dashboard_payload() -> dict[str, object] | None:
    path = DATA_DIR / "risk_diagnostic_shadow_evidence_dashboard.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_strategy_direction_rebase_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_strategy_direction_rebase.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_backtest_dataset_manifest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_backtest_dataset_manifest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_backtest_dataset_materialization_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_backtest_dataset_materialization_status.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_macro_drawdown_backtest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_macro_drawdown_backtest_result.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_macro_drawdown_robustness_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_macro_drawdown_robustness_result.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_point_in_time_phase_rebuild_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_point_in_time_phase_rebuild_status.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_late_cycle_overlay_manifest_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_late_cycle_overlay_manifest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_point_in_time_snapshot_ledger_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_point_in_time_snapshot_ledger.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_point_in_time_snapshot_ledger_status_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_point_in_time_snapshot_ledger_status.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_daily_snapshot_capture_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_daily_snapshot_capture_status.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_forward_paper_decision_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_forward_paper_decision_latest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_forward_observation_journal_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_forward_observation_journal_status.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_v15_forward_outcomes_payload() -> dict[str, object] | None:
    path = DATA_DIR / "v15_forward_outcome_status.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_research_hypotheses_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_research_hypotheses.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_validation_plan_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_validation_plan.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_experiment_templates_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_experiment_templates.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_experiment_results_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_experiment_results_phase0.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_allocation_experiment_phase1_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "allocation_experiment_phase1_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_candidate_promotion_gate_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_candidate_promotion_gate.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_research_candidate_deep_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "research_candidate_deep_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_structural_style_validation_payload() -> dict[str, object] | None:
    path = DATA_DIR / "structural_style_validation.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_structural_style_failure_analysis_payload() -> dict[str, object] | None:
    path = DATA_DIR / "structural_style_failure_analysis.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_historical_style_context_payload() -> dict[str, object] | None:
    path = DATA_DIR / "historical_style_context.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_historical_style_context_coverage_payload() -> dict[str, object] | None:
    path = DATA_DIR / "historical_style_context_coverage.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_structural_style_context_attribution_payload() -> dict[str, object] | None:
    path = DATA_DIR / "structural_style_context_attribution.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


STRATEGY_BACKTEST_IDS = {
    "defensive-dividend": "红利低波 + 现金代理防守策略",
    "industry-momentum": "行业 ETF 动量轮动 + 511880 空仓机制",
    "four-asset": "股 / 债 / 金 / 现金四资产轮动",
    "max-drawdown-batch": "最大回撤分批买入策略",
    "all-weather": "All Weather Portfolio（A股 ETF 全天候组合）",
    "equal-weight-reversion-basic": "四 ETF 等权均线回归策略（基础版）",
    "equal-weight-reversion-guarded": "四 ETF 等权均线回归策略（风控版）",
    "free-cash-flow-trend-half": "自由现金流趋势通道策略（半仓防守版）",
    "free-cash-flow-trend-full": "自由现金流趋势通道策略（满仓/空仓版）",
    "free-cash-flow-drawdown-rebound": "自由现金流回撤反弹策略（五阈值）",
    "free-cash-flow-buy-hold-480092": "自由现金流R满仓持有策略",
    "free-cash-flow-chinext-dynamic": "自由现金流R/创业板R动态满仓策略",
    "free-cash-flow-chinext-reversion": "自由现金流R/创业板R相对回归策略",
    "free-cash-flow-chinext-balanced-reversion": "自由现金流R/创业板R平衡回归策略",
    "free-cash-flow-ma-deviation": "自由现金流R均线偏离策略",
    "free-cash-flow-dual-ma-crossover": "自由现金流R双均线金叉死叉策略",
}


def _read_strategy_suite_backtest_payload(strategy_id: str) -> dict[str, object] | None:
    if strategy_id not in STRATEGY_BACKTEST_IDS:
        raise HTTPException(status_code=404, detail=f"unknown strategy backtest: {strategy_id}")
    path = DATA_DIR / "strategy_backtests" / f"{strategy_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _read_strategy_suite_summaries() -> list[dict[str, object]]:
    summaries = []
    for strategy_id in STRATEGY_BACKTEST_IDS:
        payload = _read_strategy_suite_backtest_payload(strategy_id)
        if payload and isinstance(payload.get("summary"), dict):
            summaries.append(
                {
                    "strategy_id": strategy_id,
                    "metadata": payload.get("metadata", {}),
                    "summary": payload.get("summary", {}),
                    "validation": payload.get("validation", {}),
                    "price_history": payload.get("price_history", {}),
                }
            )
    return summaries


def _compact_backtest_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "validation", "price_history")
        if key in payload
    }


def _compact_policy_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "period_validation", "policy_contradiction_audit", "data_quality", "constraints")
        if key in payload
    }


def _compact_opportunity_risk_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "current", "historical_summary", "data_quality", "constraints")
        if key in payload
    }


def _compact_opportunity_risk_policy_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "current", "summary", "period_validation", "data_quality", "constraints")
        if key in payload
    }


def _compact_policy_effectiveness_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "model_comparison", "period_validation", "data_quality", "constraints")
        if key in payload
    }


def _compact_market_phase_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "current", "historical_summary", "period_validation", "data_quality", "constraints")
        if key in payload
    }


def _compact_macro_context_history_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("rows")
    compact = {
        key: payload[key]
        for key in ("metadata", "summary", "data_quality", "constraints")
        if key in payload
    }
    if isinstance(rows, list):
        compact["sample_rows"] = rows[-5:]
    return compact


def _compact_phase_effectiveness_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "transition_analysis", "period_error_cases", "data_quality", "constraints")
        if key in payload
    }


def _compact_exposure_simulation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "current", "summary", "period_validation", "data_quality", "constraints")
        if key in payload
    }


def _compact_exposure_effectiveness_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "current", "summary", "period_validation", "data_quality", "constraints")
        if key in payload
    }


def _compact_exposure_context_analysis_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "balanced_subgroups", "context_comparison", "reason_flag_analysis", "data_quality", "constraints")
        if key in payload
    }


def _compact_balanced_context_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "candidate_states", "source_reason_summary", "data_quality", "constraints")
        if key in payload
    }


def _compact_balanced_candidate_failure_analysis_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in ("metadata", "summary", "candidate_attribution", "data_quality", "constraints")
        if key in payload
    }


def _compact_exposure_numeric_context_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("rows")
    compact = {
        key: payload[key]
        for key in ("metadata", "summary", "data_quality", "constraints")
        if key in payload
    }
    if isinstance(rows, list):
        compact["sample_rows"] = rows[-5:]
    return compact


def _compact_macro_enhanced_context_analysis_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("rows")
    compact = {
        key: payload[key]
        for key in ("metadata", "summary", "candidate_re_attribution", "sample_rows", "data_quality", "constraints")
        if key in payload
    }
    if isinstance(rows, list):
        compact["latest_rows"] = rows[-5:]
    return compact


def _compact_exposure_context_state_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("rows")
    compact = {
        key: payload[key]
        for key in ("metadata", "summary", "context_state_quality", "sample_rows", "data_quality", "constraints")
        if key in payload
    }
    if isinstance(rows, list):
        compact["latest_rows"] = rows[-5:]
    return compact


def _compact_exposure_gradient_analysis_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("rows")
    compact = {
        key: payload[key]
        for key in ("metadata", "summary", "risk_bucket_analysis", "opportunity_bucket_analysis", "data_quality", "constraints")
        if key in payload
    }
    if isinstance(rows, list):
        compact["latest_rows"] = rows[-5:]
    return compact


def _compact_risk_gradient_robustness_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "robustness",
            "period_analysis",
            "threshold_consistency",
            "overall_bucket_metrics",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_risk_gradient_condition_analysis_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "dimension_analysis",
            "composite_analysis",
            "observed_context_distribution",
            "threshold_consistency",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_risk_gradient_candidate_rules_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "candidate_rules",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_exposure_policy_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "model_comparison",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_exposure_decision_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "mode_stats",
            "separation_review",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_exposure_context_score_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "participation_bucket_analysis",
            "protection_bucket_analysis",
            "separation_review",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_protection_score_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "model_comparison",
            "bucket_metrics",
            "phase_analysis",
            "phase_consistency",
            "threshold_audit",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_two_axis_context_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "two_axis_review",
            "dimension_comparison",
            "dimension_summaries",
            "dimension_metrics",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_context_information_attribution_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "layer_attribution",
            "sample_distribution",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }


def _compact_opportunity_research_foundation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    compact = {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "coverage",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }
    rows = payload.get("asset_rows")
    if isinstance(rows, list):
        compact["asset_rows"] = rows
    return compact


def _compact_opportunity_context_features_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    compact = {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "environment_context",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }
    rows = payload.get("assets")
    if isinstance(rows, list):
        compact["sample_assets"] = rows[:5]
    return compact


def _compact_opportunity_feature_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    compact = {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }
    rows = payload.get("feature_results")
    if isinstance(rows, list):
        compact["sample_results"] = rows[:8]
    return compact


def _compact_opportunity_feature_attribution_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    compact = {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }
    rows = payload.get("feature_attribution")
    if isinstance(rows, list):
        compact["sample_attribution"] = rows[:8]
    return compact


def _compact_opportunity_v7_architecture_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "retained_layers",
            "rejected_outputs",
            "verified",
            "not_verified",
            "evidence",
            "constraints",
        )
        if key in payload
    }


def _compact_research_decision_context_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "research_context",
            "risk_context_evidence",
            "opportunity_context_evidence",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_research_decision_scenario_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    compact = {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "coverage",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }
    scenarios = payload.get("scenarios")
    if isinstance(scenarios, list):
        compact["scenarios"] = scenarios
    return compact


def _compact_research_decision_contradiction_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    compact = {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "focus_policy",
            "time_safety",
            "data_quality",
            "constraints",
        )
        if key in payload
    }
    rows = payload.get("attributions")
    if isinstance(rows, list):
        compact["attributions"] = rows
    return compact


def _compact_research_decision_v8_architecture_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "retained_layers",
            "rejected_outputs",
            "evidence",
            "constraints",
        )
        if key in payload
    }


def _compact_allocation_research_architecture_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "schema",
            "source_layer_evidence",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_research_evidence_freeze_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "hypothesis_status",
            "decision_boundary_summary",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_research_execution_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "execution_runs",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_research_result_review_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "hypothesis_review",
            "decision_boundary_audit",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_research_final_boundary_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "directions",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_external_validation_protocol_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "schema",
            "summary",
            "protocol",
            "excluded_directions",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_h2_external_validation_execution_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "validation_runs",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_h2_external_validation_result_freeze_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "final_conclusion",
            "evidence",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_research_phase_closure_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "validated_for_observation_only",
            "not_verified_for_investment_use",
            "permanent_prohibitions",
            "phase_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_research_to_implementation_boundary_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "component_boundaries",
            "implementation_entry_gate",
            "permitted_current_outputs",
            "explicitly_isolated_from_implementation",
            "source_layer_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_implementation_readiness_evidence_specification_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "readiness_schema",
            "component_readiness_specifications",
            "global_readiness_gates",
            "prohibited_shortcuts",
            "source_boundary_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_implementation_readiness_evidence_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "audit_schema",
            "component_audits",
            "global_gate_audits",
            "future_package_contract",
            "source_specification_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_research_component_evidence_submission_protocol_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "submission_schema",
            "component_submission_contracts",
            "automatic_rejection_conditions",
            "current_submission_state",
            "source_audit_framework_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_evidence_package_validation_engine_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "validation_engine",
            "current_validation_result",
            "component_validation_templates",
            "source_protocol_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_invalid_evidence_package_rejection_example_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "invalid_example_summary",
            "validator_result",
            "source_engine_evidence",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_implementation_readiness_governance_freeze_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "frozen_governance_chain",
            "implementation_boundaries",
            "not_completed",
            "recommended_next_phase",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_evidence_package_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "package_metadata",
            "component_id",
            "summary",
            "evidence_items",
            "dataset_lineage",
            "validation_results",
            "cost_turnover_capacity_review",
            "shadow_observation_log",
            "human_review_record",
            "boundary_violation_scan",
            "source_governance",
            "v12_3_audit_projection",
            "v13_2_validator_result",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_framework_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_evidence_package",
            "event_log_schema",
            "warning_event_template",
            "shadow_observation_log",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_observation_log_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_shadow_framework",
            "observation_controls",
            "event_schema_snapshot",
            "shadow_observation_log",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_observation_review_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_observation_log",
            "review_framework",
            "review_result",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_manual_event_capture_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_observation_log",
            "manual_capture_controls",
            "current_capture_result",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_event_quality_audit_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_observation_log",
            "source_manual_capture",
            "quality_audit_framework",
            "quality_audit_result",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_first_event_workflow_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_observation_log",
            "source_manual_capture",
            "source_quality_audit",
            "first_event_workflow",
            "first_event_input_requirements",
            "quality_audit_queue",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_event_input_package_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_first_event_workflow",
            "event_template",
            "json_schema",
            "validation_cli",
            "manual_submission_interface",
            "current_submission_result",
            "no_trade_guardrails",
            "promotion_gate",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_risk_diagnostic_shadow_evidence_dashboard_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "event_statistics",
            "evidence_status",
            "implementation_gate",
            "no_trade_guardrails",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_v15_strategy_direction_rebase_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    frozen_tracks = payload.get("frozen_tracks") if isinstance(payload.get("frozen_tracks"), dict) else {}
    frozen = frozen_tracks.get("v12_v14_governance_shadow") if isinstance(frozen_tracks.get("v12_v14_governance_shadow"), dict) else {}
    roadmap = payload.get("v15_roadmap") if isinstance(payload.get("v15_roadmap"), dict) else {}
    return {
        "phase": summary.get("phase"),
        "mainline_direction": summary.get("mainline_direction"),
        "direction_status": summary.get("direction_status"),
        "primary_objective": summary.get("primary_objective"),
        "secondary_objective": summary.get("secondary_objective"),
        "tertiary_objective": summary.get("tertiary_objective"),
        "v12_v14_status": frozen.get("status"),
        "not_main_alpha_strategy": frozen.get("not_main_alpha_strategy"),
        "production_trade_enabled": summary.get("production_trade_enabled"),
        "broker_connection_enabled": summary.get("broker_connection_enabled"),
        "real_order_generation_enabled": summary.get("real_order_generation_enabled"),
        "next_task": roadmap.get("v15_1"),
    }


def _compact_v15_backtest_dataset_manifest_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    dataset_groups = payload.get("dataset_groups") if isinstance(payload.get("dataset_groups"), dict) else {}
    targets = payload.get("future_backtest_targets") if isinstance(payload.get("future_backtest_targets"), dict) else {}
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    return {
        "phase": summary.get("phase") or payload.get("phase"),
        "dataset_status": summary.get("dataset_status") or payload.get("dataset_status"),
        "dataset_group_count": len(dataset_groups),
        "dataset_groups": sorted(dataset_groups.keys()),
        "future_backtest_targets": sorted(key for key, value in targets.items() if value is True),
        "does_not_run_strategy": summary.get("does_not_run_strategy") or payload.get("does_not_run_strategy"),
        "does_not_generate_position": summary.get("does_not_generate_position") or payload.get("does_not_generate_position"),
        "does_not_generate_trade_signal": summary.get("does_not_generate_trade_signal") or payload.get("does_not_generate_trade_signal"),
        "no_backtest_result": constraints.get("no_backtest_result"),
        "production_trade_enabled": summary.get("production_trade_enabled"),
        "next_task": summary.get("next_task"),
    }


def _compact_v15_backtest_dataset_materialization_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    return {
        "phase": summary.get("phase") or payload.get("phase"),
        "materialization_status": summary.get("materialization_status") or payload.get("materialization_status"),
        "dataset_groups_checked": summary.get("dataset_groups_checked") or payload.get("dataset_groups_checked"),
        "source_count": summary.get("source_count"),
        "available_source_count": summary.get("available_source_count"),
        "missing_source_count": summary.get("missing_source_count"),
        "coverage_ratio": summary.get("coverage_ratio"),
        "coverage_groups": sorted(coverage.keys()),
        "full_dataset_fetched": summary.get("full_dataset_fetched"),
        "strategy_run": summary.get("strategy_run"),
        "backtest_result_generated": summary.get("backtest_result_generated"),
        "position_generated": summary.get("position_generated"),
        "trade_signal_generated": summary.get("trade_signal_generated"),
        "production_trade_enabled": summary.get("production_trade_enabled"),
        "source_hash_recorded": quality.get("source_hash_recorded"),
        "no_broker_connection": constraints.get("no_broker_connection"),
        "next_task": summary.get("next_task"),
    }


def _compact_v15_macro_drawdown_backtest_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    benchmarks = payload.get("benchmarks") if isinstance(payload.get("benchmarks"), dict) else {}
    strategy_results = payload.get("strategy_results") if isinstance(payload.get("strategy_results"), dict) else {}
    strategy = strategy_results.get("macro_drawdown_strategy") if isinstance(strategy_results.get("macro_drawdown_strategy"), dict) else {}
    comparison = payload.get("comparison") if isinstance(payload.get("comparison"), dict) else {}
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    curve = payload.get("equity_curve") if isinstance(payload.get("equity_curve"), list) else []
    return {
        "phase": summary.get("phase") or payload.get("phase"),
        "backtest_status": summary.get("backtest_status") or payload.get("backtest_status"),
        "strategy_scope": summary.get("strategy_scope") or payload.get("strategy_scope"),
        "start_date": summary.get("start_date"),
        "end_date": summary.get("end_date"),
        "sessions": summary.get("sessions"),
        "research_backtest_only": summary.get("research_backtest_only") or payload.get("research_backtest_only"),
        "not_production_signal": summary.get("not_production_signal") or payload.get("not_production_signal"),
        "no_real_trade_order": summary.get("no_real_trade_order") or payload.get("no_real_trade_order"),
        "uses_t_plus_one_execution": payload.get("uses_t_plus_one_execution"),
        "macro_drawdown_strategy": {
            "CAGR": strategy.get("CAGR"),
            "annual_return": strategy.get("annual_return"),
            "annual_alpha": strategy.get("annual_alpha"),
            "max_drawdown": strategy.get("max_drawdown"),
            "calmar": strategy.get("calmar"),
            "sharpe": strategy.get("sharpe"),
            "drawdown_recovery_days": strategy.get("drawdown_recovery_days"),
        },
        "benchmarks": {
            key: {
                "CAGR": value.get("CAGR"),
                "max_drawdown": value.get("max_drawdown"),
                "calmar": value.get("calmar"),
            }
            for key, value in benchmarks.items()
            if isinstance(value, dict)
        },
        "comparison": {
            "beats_cash_baseline": comparison.get("beats_cash_baseline"),
            "beats_csi_300_buy_hold": comparison.get("beats_csi_300_buy_hold"),
            "beats_shanghai_composite_buy_hold": comparison.get("beats_shanghai_composite_buy_hold"),
            "improves_max_drawdown_vs_csi_300": comparison.get("improves_max_drawdown_vs_csi_300"),
            "improves_calmar_vs_csi_300": comparison.get("improves_calmar_vs_csi_300"),
            "result_must_not_be_marketed_as_success_without_beating_core_benchmarks": comparison.get(
                "result_must_not_be_marketed_as_success_without_beating_core_benchmarks"
            ),
        },
        "constraints": {
            "no_broker_connection": constraints.get("no_broker_connection"),
            "no_order_generation": constraints.get("no_order_generation"),
            "not_intraday_signal": constraints.get("not_intraday_signal"),
            "not_production_trade_signal": constraints.get("not_production_trade_signal"),
        },
        "equity_curve_rows": len(curve),
        "next_task": summary.get("next_task"),
    }


def _compact_v15_macro_drawdown_robustness_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    walk_forward = payload.get("walk_forward") if isinstance(payload.get("walk_forward"), dict) else {}
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    return {
        "phase": summary.get("phase") or payload.get("phase"),
        "validation_status": summary.get("validation_status") or payload.get("validation_status"),
        "parameter_variants": summary.get("parameter_variants"),
        "default_variant_rank": summary.get("default_variant_rank"),
        "default_CAGR": summary.get("default_CAGR"),
        "best_CAGR": summary.get("best_CAGR"),
        "worst_CAGR": summary.get("worst_CAGR"),
        "CAGR_range": summary.get("CAGR_range"),
        "calmar_range": summary.get("calmar_range"),
        "walk_forward_cost_bps": summary.get("walk_forward_cost_bps"),
        "walk_forward_CAGR": summary.get("walk_forward_CAGR"),
        "walk_forward_max_drawdown": summary.get("walk_forward_max_drawdown"),
        "walk_forward_calmar": summary.get("walk_forward_calmar"),
        "walk_forward_beats_csi_300": summary.get("walk_forward_beats_csi_300"),
        "parameter_neighborhood_stable": summary.get("parameter_neighborhood_stable"),
        "default_parameter_preferred": summary.get("default_parameter_preferred"),
        "promotion_ready": summary.get("promotion_ready"),
        "strict_point_in_time_status": summary.get("strict_point_in_time_status"),
        "research_backtest_only": summary.get("research_backtest_only") or payload.get("research_backtest_only"),
        "no_real_trade_order": summary.get("no_real_trade_order") or payload.get("no_real_trade_order"),
        "conclusion": summary.get("conclusion"),
        "next_task": summary.get("next_task"),
        "walk_forward_years": len(walk_forward.get("selections") or []),
        "selected_variant_counts": walk_forward.get("selected_variant_counts"),
        "constraints": constraints,
    }


def _compact_v15_point_in_time_phase_rebuild_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        **summary,
        "strict_point_in_time_phase_status": payload.get("strict_point_in_time_phase_status"),
        "release_date_alignment": payload.get("release_date_alignment"),
        "effective_date_alignment": payload.get("effective_date_alignment"),
        "uses_future_returns": payload.get("uses_future_returns"),
        "uses_reconstructed_labels": payload.get("uses_reconstructed_labels"),
        "publication_time_lineage_verified": payload.get("publication_time_lineage_verified"),
        "gap_count": payload.get("gap_count"),
        "promotion_ready": payload.get("promotion_ready"),
        "gaps": payload.get("gaps"),
        "constraints": payload.get("constraints"),
    }


def _compact_v15_late_cycle_overlay_manifest_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        "phase": payload.get("phase"),
        "manifest_status": payload.get("manifest_status"),
        "promotion_ready": payload.get("promotion_ready"),
        "summary": payload.get("summary"),
        "features": payload.get("features"),
        "intended_research_logic": payload.get("intended_research_logic"),
        "readiness_gate": payload.get("readiness_gate"),
        "constraints": payload.get("constraints"),
    }


def _compact_v15_point_in_time_snapshot_ledger_status_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        **summary,
        "ledger_status": payload.get("ledger_status"),
        "decision_date_count": payload.get("decision_date_count"),
        "snapshot_complete_count": payload.get("snapshot_complete_count"),
        "strict_point_in_time_eligible_count": payload.get("strict_point_in_time_eligible_count"),
        "hash_verified_count": payload.get("hash_verified_count"),
        "valuation_snapshot_available_count": payload.get("valuation_snapshot_available_count"),
        "backtest_allowed": payload.get("backtest_allowed"),
        "promotion_ready": payload.get("promotion_ready"),
        "hash_semantics": payload.get("hash_semantics"),
        "constraints": payload.get("constraints"),
    }


def _compact_v15_daily_snapshot_capture_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return payload.get("summary") if isinstance(payload.get("summary"), dict) else payload


def _compact_v15_forward_paper_decision_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload.get(key)
        for key in (
            "phase",
            "decision_date",
            "paper_only",
            "not_production_signal",
            "snapshot_manifest",
            "snapshot_manifest_sha256",
            "data_readiness",
            "readouts",
            "paper_decision",
            "constraints",
        )
    }


def _compact_v15_forward_observation_journal_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return payload.get("summary") if isinstance(payload.get("summary"), dict) else payload


def _compact_v15_forward_outcomes_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        **summary,
        "journal_record_count": payload.get("journal_record_count"),
        "outcome_record_count": payload.get("outcome_record_count"),
        "benchmark": payload.get("benchmark"),
        "paper_only": payload.get("paper_only"),
        "backtest_allowed": payload.get("backtest_allowed"),
        "production_trade_enabled": payload.get("production_trade_enabled"),
    }


def _compact_allocation_research_hypotheses_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "schema",
            "hypotheses",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_validation_plan_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "schema",
            "validation_plans",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_experiment_templates_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "schema",
            "experiment_templates",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_experiment_results_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "schema",
            "execution_scope",
            "experiment_results",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_allocation_experiment_phase1_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "schema",
            "freeze_hashes",
            "source_layer_evidence",
            "validation_results",
            "time_safety",
            "data_quality",
            "constraints",
            "audit",
        )
        if key in payload
    }


def _compact_research_candidate_promotion_gate_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_layer_evidence",
            "gate_results",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _compact_research_candidate_deep_validation_payload(payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return payload
    return {
        key: payload[key]
        for key in (
            "metadata",
            "summary",
            "source_layer_evidence",
            "deep_validation_results",
            "time_safety",
            "constraints",
            "forbidden_outputs",
            "audit",
        )
        if key in payload
    }


def _event_summary(rows: list[dict], event_key: str = "label") -> dict[str, object]:
    observations = len(rows)
    events = sum(1 for row in rows if int(row.get(event_key, 0)) == 1)
    return {
        "observations": observations,
        "events": events,
        "non_events": observations - events,
        "event_rate": round(events / observations, 6) if observations else None,
    }


def _regime_counts(rows: list[dict], regime_key: str) -> dict[str, int]:
    return dict(Counter(str(row.get(regime_key, "unknown")) for row in rows))


def _duration_summary(rows: list[dict], regime_key: str) -> dict[str, object]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        regime = str(row.get(regime_key, "unknown"))
        grouped[regime].append(int(row.get("duration", 0)))

    regimes = {}
    for regime, durations in sorted(grouped.items()):
        regimes[regime] = {
            "observations": len(durations),
            "max_duration": max(durations) if durations else 0,
            "avg_duration": round(mean(durations), 2) if durations else 0,
        }
    return regimes


def _model_validation_summary(report: dict | None) -> dict[str, object] | None:
    if not report:
        return None
    evaluation = report.get("evaluation", {})
    model = evaluation.get("model", {})
    baselines = evaluation.get("baselines", {})
    volatility = baselines.get("volatility_only", {})
    random_baseline = baselines.get("random", {})
    baseline_gap = evaluation.get("baseline_gap", {})
    return {
        "metadata": report.get("metadata", {}),
        "split": report.get("split", {}),
        "model": {
            "roc_auc": model.get("roc_auc"),
            "precision": model.get("precision"),
            "recall": model.get("recall"),
            "lift_vs_random": model.get("lift_vs_random"),
        },
        "random_baseline": {
            "roc_auc": random_baseline.get("roc_auc"),
            "precision": random_baseline.get("precision"),
        },
        "volatility_only": {
            "roc_auc": volatility.get("roc_auc"),
            "precision": volatility.get("precision"),
            "recall": volatility.get("recall"),
            "lift_vs_random": volatility.get("lift_vs_random"),
        },
        "baseline_gap": baseline_gap,
    }


def _policy_summary(policy: dict[str, dict[str, object]]) -> dict[str, object]:
    regimes = {}
    for regime in ("bull", "range", "bear", "transition"):
        regime_policy = policy.get(regime, {})
        regimes[regime] = {
            "base_exposure": regime_policy.get("base_exposure"),
            "min_exposure": regime_policy.get("min_exposure"),
            "max_exposure": regime_policy.get("max_exposure"),
            "leverage_allowed": regime_policy.get("leverage_allowed"),
            "strategy_mode": regime_policy.get("strategy_mode"),
        }
    return {"risk": policy.get("risk", {}), "regimes": regimes}


def _portfolio_policy_summary(policy: dict[str, dict[str, object]]) -> dict[str, object]:
    regimes = {}
    for regime in ("bull", "range", "bear", "transition"):
        regime_policy = policy.get(regime, {})
        regimes[regime] = {
            "base_exposure": regime_policy.get("base_exposure"),
            "max_exposure": regime_policy.get("max_exposure"),
            "min_cash": regime_policy.get("min_cash"),
            "strategy_allocation": regime_policy.get("strategy_allocation", {}),
        }
    return {"regimes": regimes}


def _strategy_policy_summary(policy: dict[str, dict[str, object]]) -> dict[str, object]:
    regimes = {}
    for regime in ("bull", "range", "bear", "transition"):
        regime_policy = policy.get(regime, {})
        regimes[regime] = {
            "enabled": regime_policy.get("enabled", []),
            "disabled": regime_policy.get("disabled", []),
        }
    return {
        "risk": policy.get("risk", {}),
        "regimes": regimes,
    }


def _execution_policy_summary(policy: dict[str, dict[str, object]]) -> dict[str, object]:
    regimes = {}
    for regime in ("bull", "range", "bear", "transition"):
        regime_policy = policy.get(regime, {})
        regimes[regime] = {
            "execution_mode": regime_policy.get("execution_mode"),
            "allow": regime_policy.get("allow", []),
            "forbid": regime_policy.get("forbid", []),
        }
    return {
        "risk": policy.get("risk", {}),
        "regimes": regimes,
    }


def _current_regime_payload() -> dict:
    end_date = _today_text()
    start_date = _calendar_shift(end_date, -540)
    index_df = _load_index_window(start_date, end_date)
    as_of = str(index_df["trade_date"].iloc[-1])
    market_daily = get_market_daily(as_of)
    history_start = _calendar_shift(as_of, -370)
    market_history = get_market_history_sample(
        market_daily,
        history_start,
        as_of,
        sample_size=BREADTH_HISTORY_SAMPLE_SIZE,
    )
    hsgt = _load_hsgt_for_index(index_df, as_of)
    return analyze_index_regime(
        index_df,
        market_daily_df=market_daily,
        market_history_df=market_history,
        hsgt_df=hsgt,
    )


def _current_portfolio_snapshot() -> dict[str, object]:
    current = _current_regime_payload()
    risk_signal = adapt_regime_payload(current)
    risk_policy = load_risk_policy()
    exposure_decision = build_exposure_decision(risk_signal, policy=risk_policy)
    portfolio_policy = load_portfolio_policy()
    portfolio_allocation = build_portfolio_allocation(
        {"input": risk_signal, "decision": exposure_decision},
        policy=portfolio_policy,
    )
    strategy_policy = load_strategy_policy()
    strategy_route = build_strategy_route(portfolio_allocation, policy=strategy_policy)
    execution_policy = load_execution_policy()
    execution = simulate_execution_layer(strategy_route, policy=execution_policy)
    return {
        "current": current,
        "risk_signal": risk_signal,
        "risk_policy": risk_policy,
        "risk_decision": exposure_decision,
        "portfolio_policy": portfolio_policy,
        "portfolio_allocation": portfolio_allocation,
        "strategy_policy": strategy_policy,
        "strategy_route": strategy_route,
        "execution_policy": execution_policy,
        "execution": execution,
    }


def _system_snapshot_payload(snapshot: dict[str, object]) -> dict[str, object]:
    portfolio = snapshot["portfolio_allocation"]
    strategy_route = snapshot["strategy_route"]
    execution = snapshot["execution"]
    boundaries = {
        "no_stock_selection": portfolio["constraints"]["no_stock_selection"] is True,
        "no_trade_execution": strategy_route["constraints"]["no_trade_execution"] is True,
        "no_real_orders": execution["constraints"]["no_real_orders"] is True,
        "no_broker_connection": execution["constraints"]["no_broker_connection"] is True,
        "simulation_only": execution["constraints"]["simulated_only"] is True,
    }
    policy_locked = (ROOT_DIR / "rules" / "LOCKED_POLICY.md").exists()
    freeze_doc_present = (ROOT_DIR / "docs" / "system_architecture_freeze.md").exists()
    decision_trace_present = (ROOT_DIR / "logs" / "decision_trace.json").exists()
    stable = all(boundaries.values()) and policy_locked and freeze_doc_present and decision_trace_present
    return {
        "status": "stable" if stable else "review_required",
        "as_of": snapshot["current"]["as_of"],
        "layers": 5,
        "execution_mode": "simulation",
        "risk_engine": "active",
        "policy_locked": policy_locked,
        "freeze_doc_present": freeze_doc_present,
        "decision_trace_present": decision_trace_present,
        "boundaries": boundaries,
        "current": {
            "regime": snapshot["risk_signal"]["regime"],
            "risk_level": snapshot["risk_decision"]["risk_level"],
            "total_exposure": portfolio["total_exposure"],
            "enabled_strategies": strategy_route["enabled_strategies"],
            "execution_mode": execution["strategy_mode"],
            "simulated_order_count": execution["constraints"]["order_count"],
        },
        "artifacts": {
            "architecture_freeze": "docs/system_architecture_freeze.md",
            "decision_trace": "logs/decision_trace.json",
            "policy_lock": "rules/LOCKED_POLICY.md",
            "integrity_check": "scripts/system_integrity_check.py",
        },
    }


def _meta_edge_payload(snapshot: dict[str, object]) -> dict[str, object]:
    return build_meta_edge_signal(
        regime_signal=snapshot["risk_signal"],
        risk_decision=snapshot["risk_decision"],
        portfolio=snapshot["portfolio_allocation"],
        strategy_route=snapshot["strategy_route"],
        hazard_rows=_read_data_json("structural_hazard_dataset.json") or [],
        survival_rows=_read_data_json("structural_survival_dataset.json") or [],
        rules=load_meta_edge_rules(),
    )


def _style_rotation_payload(snapshot: dict[str, object]) -> dict[str, object]:
    style_factor = build_style_factor_snapshot(
        regime_signal=snapshot["risk_signal"],
        risk_decision=snapshot["risk_decision"],
    )
    etf_universe = build_etf_universe(style_factor)
    return {
        "as_of": snapshot["current"]["as_of"],
        "task": "A1.1",
        "style_factor": style_factor,
        "etf_universe": etf_universe,
        "interpretation": {
            "primary_style": (style_factor["top_styles"][0]["style"] if style_factor["top_styles"] else None),
            "primary_candidate": (
                etf_universe["top_candidates"][0] if etf_universe["top_candidates"] else None
            ),
            "summary": (
                "当前层把市场状态、风险评分、宽度、流动性和波动稳定度转成风格倾向，"
                "再映射到 ETF 候选池；它只做资产风格与 ETF universe 生成，不做个股选择或真实交易。"
            ),
        },
    }


def _etf_price_history_from_cache(
    etf_universe: dict[str, object],
    as_of: str,
    lookback_days: int = 320,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], str]:
    start_date = _calendar_shift(as_of, -lookback_days)
    price_history: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for candidate in etf_universe.get("candidates", []):
        code = str(candidate["code"])
        frame = read_benchmark_cache(code, start_date, as_of)
        if frame.empty:
            errors[code] = "fund_daily cache missing or empty"
            continue
        price_history[code] = frame
    return price_history, errors, start_date


def _etf_rotation_signal_payload(style_rotation: dict[str, object]) -> dict[str, object]:
    style_factor = style_rotation["style_factor"]
    etf_universe = style_rotation["etf_universe"]
    as_of = str(style_rotation["as_of"])
    price_history, price_errors, start_date = _etf_price_history_from_cache(etf_universe, as_of)
    rotation_signal = build_etf_rotation_signal(style_factor, etf_universe, price_history)
    rotation_signal["price_history"] = {
        "start_date": start_date,
        "end_date": as_of,
        "errors": price_errors,
        "source": "local fund_daily cache",
    }
    return rotation_signal


def _api_endpoint(
    method: str,
    path: str,
    description: str,
    returns: str,
    params: list[dict[str, str]] | None = None,
    freshness: str = "current",
    safety: str = "read-only",
) -> dict[str, object]:
    return {
        "method": method,
        "path": path,
        "description": description,
        "params": params or [],
        "returns": returns,
        "freshness": freshness,
        "safety": safety,
    }


def _api_catalog_payload() -> dict[str, object]:
    groups = [
        {
            "name": "Web 与接口文档",
            "description": "页面入口、接口目录和自动生成文档。",
            "endpoints": [
                _api_endpoint("GET", "/", "打开宏观周期总览首页。", "HTML dashboard", freshness="page"),
                _api_endpoint("GET", "/v2", "打开 V2 研究总览，展示宏观、结构、行业机会、主题风险、配置意图和决策追踪。", "HTML dashboard", freshness="page"),
                _api_endpoint("GET", "/v2-validation", "打开 V2 验证页面，查看 V2 配置意图回测、基准对比和状态归因。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/risk-execution", "兼容旧链接；风控执行内容已合并到首页展示。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategies", "打开策略回测频道，集中查看策略信号、关键回测摘要和策略入口。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/validation", "打开验证归因频道，集中查看仓位风控回测、Regime 归因、结构事件和模型验证。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/v15-formal-evaluation", "打开V15正式评价页，使用沪深300全收益、2016起点和15bp成本展示全周期与样本外结论。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/etf-rotation", "打开 ETF 轮动策略主页，集中查看回测图、关键指标和调仓历史入口。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/macro-style", "打开 Macro-Style-ETF 分层策略主页，集中查看回测图、关键指标和调仓历史入口。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/defensive-dividend", "打开红利低波 + 现金代理防守策略主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/industry-momentum", "打开行业 ETF 动量轮动 + 511880 空仓机制策略主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/four-asset", "打开股 / 债 / 金 / 现金四资产轮动策略主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/max-drawdown-batch", "打开最大回撤分批买入策略主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/all-weather", "打开 All Weather Portfolio（A股 ETF 全天候组合）策略主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/equal-weight-reversion-basic", "打开四 ETF 等权均线回归策略基础版主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/equal-weight-reversion-guarded", "打开四 ETF 等权均线回归策略风控版主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-trend-half", "打开自由现金流趋势通道半仓防守版主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-trend-full", "打开自由现金流趋势通道满仓/空仓版主页。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-drawdown-rebound", "打开自由现金流回撤反弹策略主页，查看五个 n 阈值净值曲线。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-buy-hold-480092", "打开自由现金流R满仓持有策略主页，查看全收益指数对比和历史回顾背景图。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-chinext-dynamic", "打开自由现金流R/创业板R动态满仓策略主页，查看动态权重和双指数对比。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-chinext-reversion", "打开自由现金流R/创业板R相对回归策略主页，查看相对比值 Z-score 和双指数对比。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-chinext-balanced-reversion", "打开自由现金流R/创业板R平衡回归策略主页，查看底仓、回归确认和双指数对比。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-ma-deviation", "打开自由现金流R均线偏离策略主页，查看 MA 偏离带、默认参数和全样本参数扫描。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/strategy/free-cash-flow-dual-ma-crossover", "打开自由现金流R双均线金叉死叉策略主页，查看快慢均线、交叉信号和参数扫描。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/rotation-history", "打开 ETF 轮动调仓历史表格页面。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/macro-style-history", "打开 Macro-Style-ETF 分层组合调仓历史表格页面。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/cycle-track", "打开后市展望页面。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/cycle-observation", "打开历史回顾页面。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/api-docs", "打开接口说明页面。", "HTML page", freshness="page"),
                _api_endpoint("GET", "/api", "返回当前系统所有主要接口、用途、参数和边界说明。", "API catalog"),
                _api_endpoint("GET", "/docs", "打开 FastAPI 交互式接口文档。", "Swagger UI", freshness="docs"),
                _api_endpoint("GET", "/redoc", "打开 ReDoc 接口文档。", "ReDoc HTML", freshness="docs"),
                _api_endpoint("GET", "/openapi.json", "返回机器可读 OpenAPI 规范。", "OpenAPI schema", freshness="docs"),
                _api_endpoint("GET", "/api/health", "服务健康检查。", "status"),
            ],
        },
        {
            "name": "市场状态识别",
            "description": "读取当前市场状态、四维评分、解释和历史序列。",
            "endpoints": [
                _api_endpoint("GET", "/api/regime/current", "当前 A 股牛熊状态、置信度和四维评分。", "current regime"),
                _api_endpoint("GET", "/api/features/latest", "当前最新四维特征分数。", "latest feature scores"),
                _api_endpoint("GET", "/api/regime/explain", "当前状态识别的文字解释。", "regime explanation"),
                _api_endpoint(
                    "GET",
                    "/api/regime/score-history",
                    "从本轮牛市起点开始的四维评分历史，并叠加上证指数收盘价；默认只读缓存，fill_tail=true 时补算缺失尾部。",
                    "cycle score history",
                    params=[{"name": "fill_tail", "required": "false", "format": "boolean"}],
                ),
                _api_endpoint(
                    "GET",
                    "/api/regime/history",
                    "指定时间段内的状态序列，最多 80 个交易日。",
                    "history items",
                    params=[
                        {"name": "start", "required": "true", "format": "YYYYMMDD"},
                        {"name": "end", "required": "true", "format": "YYYYMMDD"},
                    ],
                ),
            ],
        },
        {
            "name": "V2 宏观数据基础",
            "description": "V2 Macro Data Foundation 的只读状态，展示指标注册表、缓存覆盖和时间安全审计；不判断牛熊、不计算仓位。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/macro/data-status",
                    "返回宏观指标注册表、本地缓存可用性、缺失指标和未来函数检查结果。",
                    "macro data audit",
                    params=[
                        {"name": "start_date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "end_date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "decision_date", "required": "false", "format": "YYYYMMDD"},
                    ],
                    freshness="local macro cache",
                ),
                _api_endpoint(
                    "GET",
                    "/api/macro/current",
                    "返回 V2.2 Macro Cycle Engine 的当前宏观分数、状态、置信度、解释和数据质量；不输出仓位或交易建议。",
                    "macro cycle snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "start_date", "required": "false", "format": "YYYYMMDD"},
                    ],
                    freshness="local macro cache",
                ),
                _api_endpoint(
                    "GET",
                    "/api/macro/context-history",
                    "返回 V5.7 历史宏观上下文，按 exposure replay 日期给出 release/effective-date 安全的宏观分数、组件、指标值和 source trace；缺失保持 null。",
                    "historical macro context",
                    freshness="generated artifact",
                ),
            ],
        },
        {
            "name": "V2 市场结构",
            "description": "独立于宏观周期的市场结构识别，只看指数趋势、宽度、流动性和后续可接入的行业/主题强度；不输出仓位、ETF 配置或交易信号。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/structure/current",
                    "返回 V2.3 Market Structure Engine 的当前市场结构状态、结构分、置信度、指标和解释。",
                    "market structure snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "start_date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "history_sample_size", "required": "false", "format": "0-100"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="index and local breadth/liquidity cache",
                ),
            ],
        },
        {
            "name": "V2 行业/主题机会",
            "description": "识别是否存在结构性赚钱机会和持续主线，只输出行业强度、主线持续性和数据来源；不输出仓位、ETF 配置或交易信号。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/industry/opportunity",
                    "返回 V2.3 Industry / Theme Opportunity Engine 的行业机会分、主线持续性、Top 行业和数据质量。",
                    "industry opportunity snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "start_date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="Tushare industry index cache",
                ),
            ],
        },
        {
            "name": "V2 结构性牛市探测",
            "description": "融合宏观周期、市场结构和行业机会三层证据，只判断当前结构环境；不输出仓位、ETF 配置或交易信号。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/structural-bull/current",
                    "返回 V2.3 Structural Bull Rotation Detector 的结构状态、评分、置信度和三层证据链。",
                    "structural bull snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="macro, market structure and industry opportunity cache",
                ),
            ],
        },
        {
            "name": "V2 主题风险过滤",
            "description": "判断强主线是否存在价格延伸、位置偏高、宽度不足和集中度风险；不改变结构牛状态，不输出交易动作。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/theme-risk/current",
                    "返回 V2.3 Theme Valuation & Crowding Risk Layer 的机会质量、拥挤分、过热警示和数据质量。",
                    "theme risk snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "start_date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="industry opportunity cache",
                ),
            ],
        },
        {
            "name": "V2 配置意图",
            "description": "融合宏观、结构、行业机会和主题风险，只输出风险预算、权益区间和风格偏好；不输出 ETF 代码、买卖或下单。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/allocation/intent",
                    "返回 V2.4 Adaptive Allocation Intent Engine 的配置意图、证据链和边界约束。",
                    "allocation intent snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="macro, structure, opportunity and theme risk cache",
                ),
            ],
        },
        {
            "name": "V2 配置决策追踪",
            "description": "解释从宏观、结构、行业机会、主题风险到配置意图的调整路径和冲突项；不改变配置意图。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/allocation/trace",
                    "返回 V2.4 Allocation Decision Trace 的分层影响、调整路径、冲突检测和审计结果。",
                    "allocation decision trace",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="allocation intent cache",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/overview",
                    "返回 V2 研究总览聚合结果，串联宏观、结构、行业机会、结构牛、主题风险、配置意图和决策追踪。",
                    "v2 overview snapshot",
                    params=[
                        {"name": "date", "required": "false", "format": "YYYYMMDD"},
                        {"name": "cache_only", "required": "false", "format": "boolean"},
                    ],
                    freshness="current v2 cache",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/backtest",
                    "返回 V2.5.1 配置意图验证回测结果，包含 T+1 净值曲线、宽基/旧系统基准对比和状态归因。",
                    "v2 allocation validation backtest",
                    freshness="generated artifact",
                    safety="read-only artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/policy-sensitivity",
                    "返回 V2.5.2 风险预算映射敏感性结果和长历史覆盖审计。",
                    "v2 allocation policy sensitivity",
                    freshness="generated artifact",
                    safety="read-only artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/structural-policy",
                    "返回 V2.5.3 结构牛配置细分政策分析，说明健康/均衡/过热结构牛如何影响风险预算。",
                    "v2 structural bull policy analysis",
                    freshness="generated artifact",
                    safety="read-only artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/full-cycle-validation",
                    "返回 V2.6.1 完整周期目标覆盖审计、当前真实可验证窗口、缺口和 V2 baseline/refined/基准对比。",
                    "v2 full-cycle validation audit",
                    freshness="generated artifact",
                    safety="read-only artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/history-expansion",
                    "返回 V2.6.2 历史数据基础扩展审计，展示 2015 起覆盖进展、剩余缺口和数据来源边界。",
                    "v2 historical data expansion audit",
                    freshness="generated artifact",
                    safety="read-only artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/v2/full-cycle-backtest",
                    "返回 V2.6.3 2015 起完整窗口 walk-forward 回测，包含基准对比、阶段归因、结构牛贡献和宏观软缺口披露。",
                    "v2 full-cycle walk-forward backtest",
                    freshness="generated artifact",
                    safety="read-only artifact",
                ),
            ],
        },
        {
            "name": "后市展望与历史回顾",
            "description": "历史周期切分、后市展望和概率展望。",
            "endpoints": [
                _api_endpoint("GET", "/api/regime/cycle", "历史主周期、指数序列和周期主题块。", "major cycle analysis"),
                _api_endpoint("GET", "/api/regime/cycle/track", "后市展望所需的当前主周期起点、当前位置、关键均线和概率。", "current cycle track"),
            ],
        },
        {
            "name": "组合与策略模拟",
            "description": "从风险状态到组合、策略路由和执行模拟的只读决策链。",
            "endpoints": [
                _api_endpoint("GET", "/api/portfolio/current", "当前组合仓位、现金比例和策略资金分配。", "portfolio allocation"),
                _api_endpoint("GET", "/api/strategy/current", "当前可启用策略、禁用策略和策略预算。", "strategy route"),
                _api_endpoint("GET", "/api/execution/current", "执行意图和模拟指令，不产生真实订单。", "execution simulation"),
            ],
        },
        {
            "name": "Small Edge Meta Signal",
            "description": "检测风控、组合、策略和结构风险之间的内部矛盾，不预测收益、不选股。",
            "endpoints": [
                _api_endpoint("GET", "/api/meta-edge/current", "当前 Meta Signal Engine v1 快照。", "meta edge signal"),
            ],
        },
        {
            "name": "风格轮动 Alpha",
            "description": "把当前状态与风险输入映射为风格评分和 ETF 候选池；只做 universe 生成，不选股、不下单。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/style/current",
                    "返回 A1.1 风格评分、Top 风格、ETF universe 和候选 ETF 排名。",
                    "style factor and ETF universe",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/rotation-signal",
                    "返回 A1.2 ETF 轮动信号、相对强弱、目标权重建议和置信度。",
                    "ETF rotation signal",
                    freshness="generated from local ETF cache",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/rotation-backtest",
                    "返回 A1.3 ETF 轮动回测、Alpha 验证、benchmark 对比和分状态拆解；收益口径优先使用 fund_daily pct_chg/pre_close。",
                    "ETF rotation backtest",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/macro-style-etf-backtest",
                    "返回 M2.1 Macro-Style-ETF 三层分层组合回测，比较 510300、510500、等权 ETF basket 和当前 A1 系统。",
                    "Macro-Style-ETF hierarchical backtest",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/alpha/portfolio-risk-validation",
                    "返回 V3.4.3 Alpha 组合风险控制验证，展示固定调仓周期、成本、最低持有期和主题集中度敏感性；只读研究产物，不生成交易指令。",
                    "alpha portfolio risk-control validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/alpha/robustness-validation",
                    "返回 V3.4.4 Alpha 组合滚动稳健性和风格归因验证，判断收益来自 Alpha 还是风格暴露；只读研究产物。",
                    "alpha robustness and style attribution validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/alpha/residual-alpha-analysis",
                    "返回 V3.4.5 残差 Alpha 与因子中性化归因，拆解市场/风格 Beta 和因子剥离后的残差收益；只读研究产物。",
                    "residual alpha attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/allocation-snapshot",
                    "返回 V3.5.1 风格配置引擎基础快照，把宏观、结构、主题风险和 Alpha 风格暴露映射为风格偏好；不是 ETF 权重、仓位或交易信号。",
                    "regime-aware style preference snapshot",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/validation",
                    "返回 V3.5.2 风格偏好验证与归因，比较原始机会分 TopN 与风格偏好筛选池的 20/60 日未来收益、IC、spread 和 hit rate；只读研究验证。",
                    "style preference validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/incremental-analysis",
                    "返回 V3.5.7 风格偏好增量信息检验，比较 Opportunity、Style 和固定 50/50 Combined 三套排序的 IC、TopN 收益差和分状态结果；只读研究验证。",
                    "style incremental information test",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/policy",
                    "返回 V4.1 Allocation Policy Foundation，把宏观、结构、主题风险、风格偏好和 V3.5.7 增量结论转成定性 Beta 风险预算约束；不是 ETF 权重、仓位或交易信号。",
                    "regime-aware beta allocation policy foundation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/policy-validation",
                    "返回 V4.2 Risk Budget Historical Validation，把固定 V4.1 风险预算规则在 2015 起历史状态中重放，输出阶段分布、矛盾审计和复核项；不调规则、不输出仓位、不生成交易。",
                    "risk budget historical validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/opportunity-risk",
                    "返回 V4.3 Market Opportunity vs Risk State，把机会状态和风险状态拆成两个轴，并给出当前状态、历史分布和证据链；不输出仓位、ETF 或交易信号。",
                    "market opportunity/risk state separation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/opportunity-risk-policy",
                    "返回 V4.4 Opportunity-Risk Policy Mapping Validation，把机会状态 + 风险状态映射为定性政策模式，并做历史重放分布验证；不输出仓位、ETF、权重或交易信号。",
                    "opportunity/risk qualitative policy mapping",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/policy-effectiveness",
                    "返回 V4.5 Policy Effectiveness Audit，把固定 V4.4 政策模式与旧 structural_state、机会风险二维状态做事后环境解释力和矛盾率对比；只做验证，不调阈值、不输出仓位或交易。",
                    "policy effectiveness counterfactual validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/market-phase",
                    "返回 V4.6 Market Phase Classification Layer，在机会和风险之外新增 Early/Expansion/Rotation/Late/Contraction 第三维阶段解释，并做历史重放；不输出仓位、ETF、权重或交易。",
                    "market phase classification layer",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/phase-effectiveness",
                    "返回 V4.7 Market Phase Effectiveness Audit，固定 V4.6 阶段规则，审计 phase 相对 structural_state 的风险区分力、阶段转移和错误案例；不调阈值、不输出仓位或交易。",
                    "market phase effectiveness audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-simulation",
                    "返回 V5.1 Adaptive Exposure Policy Simulation，把固定政策模式映射为 DEFENSIVE/LOW/BALANCED/HIGH/OFFENSIVE 定性暴露等级，并审计历史矛盾和机会错失；只输出定性等级，不输出仓位百分比、ETF、权重或交易信号。",
                    "qualitative exposure policy simulation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-effectiveness",
                    "返回 V5.2 Exposure Level Effectiveness Audit，固定 V5.1 暴露等级不改规则，审计等级分布、风险/机会区分、有序性和 HIGH/OFFENSIVE 缺失原因；不输出仓位、ETF、权重或交易信号。",
                    "qualitative exposure effectiveness audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-context-analysis",
                    "返回 V5.3 Exposure Context Decomposition Audit，只分析固定 V5.1 的 BALANCED 桶，拆解失败、机会错失和中性样本的上下文来源；不修改规则、不增加等级、不输出仓位或交易。",
                    "balanced exposure context decomposition audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/balanced-context-audit",
                    "返回 V5.4 Balanced Context Candidate State Audit，基于 V5.3 输出审计 BALANCED_RISK/BALANCED_OPPORTUNITY/BALANCED_NEUTRAL 研究候选标签质量；不修改 mapper、不新增正式等级、不输出仓位或交易。",
                    "balanced context candidate state audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/balanced-candidate-failure-analysis",
                    "返回 V5.5 Balanced Candidate Failure Attribution，固定 V5.4 候选标签归因 BALANCED_RISK 失败和 BALANCED_OPPORTUNITY 机会错失；不修改 mapper、不新增状态、不输出仓位或交易。",
                    "balanced candidate failure attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-numeric-context",
                    "返回 V5.6 Numeric Context Enrichment，把每个历史定性暴露信号与当时可见的宏观、结构、行业主题和风险数值上下文关联；缺失保持 null，不做未来填充，不改规则。",
                    "time-safe exposure numeric context",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/macro-enhanced-context-analysis",
                    "返回 V5.8 Macro-Enhanced Exposure Context Re-Attribution，固定 V5.4 BALANCED 候选标签，结合 V5.6 数值上下文和 V5.7 宏观历史上下文重新归因；只做解释审计，不新增正式状态、不改 mapper、不输出仓位或交易。",
                    "macro-enhanced balanced attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-context-state-audit",
                    "返回 V5.9 Exposure Context State Model Design Audit，把 BALANCED 拆成 Recovery、Structural Opportunity、Risk、Neutral 研究候选状态并审计样本、未来风险/机会率、置信度和分离度；不新增正式状态、不改 mapper、不输出仓位或交易。",
                    "research-only exposure context state audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-gradient-analysis",
                    "返回 V5.10 Exposure Context Risk Gradient Analysis，在 BALANCED 内构建连续风险/机会梯度并分桶验证未来风险和机会区分力；固定权重、非参数优化，不改 mapper、不输出仓位或交易。",
                    "continuous risk/opportunity gradient audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/risk-gradient-robustness",
                    "返回 V5.11 Risk Gradient Robustness & Stability Audit，固定 V5.10 风险梯度权重和阈值做分阶段稳健性审计；不改 mapper、仓位、ETF 或交易。",
                    "risk gradient stability audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/risk-gradient-condition-analysis",
                    "返回 V5.12 Risk Gradient Conditional Validation，固定 V5.10 风险分数和 V5.11 阈值，按机会状态、市场阶段、风险状态及组合条件审计高风险梯度何时有效；不形成规则。",
                    "risk gradient conditional validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/risk-gradient-candidate-rules",
                    "返回 V5.13 Risk Gradient Minimal Rule Candidate Audit，只从 V5.12 正向条件中抽取有限候选并审计覆盖、稳定性和失败案例；不输出正式规则。",
                    "minimal risk candidate audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-policy-validation",
                    "返回 V6.1 Adaptive Exposure Policy Simulation Validation，固定 V5.1 暴露模拟并叠加 V5 风险诊断，审计捕获率、误警率、冲突覆盖率；不改仓位或策略。",
                    "diagnostic-only exposure policy validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-decision-audit",
                    "返回 V6.2 Adaptive Exposure Decision Layer Design Audit，把机会、风险和梯度组合成研究型 decision context 标签并审计风险/机会分离度；不输出仓位。",
                    "research-only exposure decision context audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/exposure-context-score-audit",
                    "返回 V6.3 Continuous Exposure Context Score Audit，生成 participation/protection 连续研究分数并审计风险/机会分离度；不改策略。",
                    "continuous exposure context score audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/protection-score-validation",
                    "返回 V6.4 Protection Score Robustness & Conditional Validation，固定 V6.3 保护分、V5.10 风险梯度和 V5.11 阈值，对比未来高风险、回撤和矛盾率；不改仓位或策略。",
                    "protection score robustness validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/two-axis-context-validation",
                    "返回 V6.5 Adaptive Context Two-Axis Validation，固定 V6.3 participation/protection 分桶生成二维环境象限，并与 V5.1 暴露等级、V6.2 decision mode 对比未来风险、机会、回撤和矛盾率；不改策略。",
                    "adaptive context two-axis validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation/context-information-attribution",
                    "返回 V6.6 Adaptive Context Information Attribution Audit，对 V5.1 暴露等级、V5.10 风险梯度、V6.3 保护分、V6.5 双轴上下文做信息增量归因，判断保留/淘汰；不新增模型或策略。",
                    "adaptive context information attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/opportunity/research-foundation",
                    "返回 V7.1 Opportunity / Asset Research Layer Foundation，汇总 ETF 资产池、长历史研究代理、真实可交易历史覆盖率和时间安全边界；不生成评分、排名、仓位或交易信号。",
                    "opportunity research foundation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/opportunity/context-features",
                    "返回 V7.2 Structural Opportunity Context Feature Audit，按统一安全日期输出动量、相对强弱、趋势、风险和结构特征字段；不生成机会分、排名、Top N、仓位或交易信号。",
                    "opportunity context feature audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/opportunity/feature-validation",
                    "返回 V7.3 Opportunity Feature Effectiveness Audit，用固定 V7.2 字段审计 5/20/60 日 IC、research proxy 与真实 ETF 可交易迁移效果；不生成评分、排名、Top N、仓位或交易信号。",
                    "opportunity feature effectiveness audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/opportunity/feature-attribution",
                    "返回 V7.4 Opportunity Feature Attribution & Stability Audit，固定 V7.3 结果做特征保留/观察/暂弃归因和环境稳定性审计；不生成评分、权重、排名、Top N、仓位或交易信号。",
                    "opportunity feature attribution audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/opportunity/v7-architecture",
                    "返回 V7.5 Opportunity Research Layer Freeze，汇总 V7.1-V7.4 保留层、显式拒绝的评分/排名/配置/交易输出，以及冻结边界审计脚本。",
                    "opportunity V7 architecture freeze",
                    freshness="generated doc and existing artifacts",
                ),
                _api_endpoint(
                    "GET",
                    "/api/decision/research-context",
                    "返回 V8.1 Research Decision Integration Architecture，把冻结的 V6 风险上下文与 V7 机会研究归因整合为只读研究语境；不输出资产、排名、Top N、仓位、ETF 权重或交易信号。",
                    "research decision context",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/decision/scenario-audit",
                    "返回 V8.2 Research Decision Historical Scenario Audit，审计 V8.1 研究语境在固定历史情景中的解释一致性、切换稳定、矛盾和覆盖缺口；不使用收益指标，不输出策略。",
                    "research decision scenario audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/decision/contradiction-attribution",
                    "返回 V8.3 Research Decision Contradiction Attribution，归因 2015、2018、2021、2024-2026 等重点场景的解释失败原因；不修改 V6/V7，不新增状态、评分、配置或交易。",
                    "research decision contradiction attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/decision/v8-architecture",
                    "返回 V8.4 Research Decision Architecture Freeze，汇总 V8.1-V8.3 保留层、显式拒绝的评分/排名/资产选择/配置/交易输出，以及冻结边界审计脚本。",
                    "research decision V8 architecture freeze",
                    freshness="generated doc and existing artifacts",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/architecture",
                    "返回 V9.1 Allocation Research Architecture Foundation，定义未来配置研究层的输入、证据要求和禁止输出；不生成资产选择、ETF 映射、权重、回测优化或交易信号。",
                    "allocation research architecture",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/hypotheses",
                    "返回 V9.2 Allocation Research Hypothesis Framework，只定义未来配置研究假设；所有假设均为 unvalidated，不输出资产、ETF、权重、回测结果、优化或交易信号。",
                    "allocation research hypotheses",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/validation-plan",
                    "返回 V9.3 Allocation Research Validation Plan Framework，只设计 V9.2 假设的验证方法；不执行验证、不输出回测结果、不做参数优化或交易。",
                    "allocation research validation plan",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/experiment-templates",
                    "返回 V9.4 Allocation Research Experiment Template Framework，只定义预声明实验模板；不运行实验、不输出结果、不定义资产、ETF、权重或交易。",
                    "allocation research experiment templates",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/experiment-results",
                    "返回 V9.5 Allocation Research Experiment Execution Phase 0，只执行预声明模板的研究纪律检查；不读取市场数据、不输出回测结果、资产、ETF、权重或交易。",
                    "allocation research experiment results phase 0",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/experiment-phase1-validation",
                    "返回 V9.6 Allocation Research Experiment Phase 1 Validation，用冻结 V6/V7/V8/V9.5 产物验证预声明实验；输出 supported/inconclusive/unsupported 研究状态，不生成配置或交易。",
                    "allocation research experiment phase 1 validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/research-candidate-gate",
                    "返回 V9.7 Research Candidate Promotion Gate Audit，只审计假设是否继续研究、冻结或暂拒；promotion_allowed=false，不生成策略、配置、资产、ETF、权重或交易。",
                    "allocation research-stage gate audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/research-candidate-deep-validation",
                    "返回 V9.8 Research Candidate Deep Validation Framework，对 H2/H4 继续研究假设做更严格的场景一致性与矛盾门禁验证；仍不策略化、不配置、不优化、不交易。",
                    "allocation research candidate deep validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/evidence-freeze",
                    "返回 V9.9 Allocation Research Evidence Freeze，冻结 V9.1-V9.8 研究证据边界：H2/H4 仅保留研究方向，H1/H3 暂停；不策略化、不配置、不优化、不交易。",
                    "allocation research evidence freeze",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/execution-runs",
                    "返回 V10.1 Allocation Research Execution Framework，基于 V9.9 和冻结 V6/V7/V8 产物生成 H2/H4 可复现实验运行记录；不选资产、不映射ETF、不生成权重、不优化、不交易。",
                    "allocation research execution runs",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/result-review",
                    "返回 V10.2 Allocation Research Result Review，审查 V10.1 执行结果并冻结 H2/H4 决策边界；不策略化、不配置、不优化、不交易。",
                    "allocation research result review",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/allocation-research/final-boundary",
                    "返回 V10.3 Allocation Research Final Boundary Decision，冻结 V9-V10 最终研究边界：H2 只可继续外部验证，H4 仅保留为研究治理，H1/H3 冻结；不策略化、不配置、不优化、不交易。",
                    "allocation research final boundary",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/external-validation/protocol",
                    "返回 V11.1 External Validation Research Protocol，只为 H2 定义外部验证协议、预注册窗口、失败标准和停止条件；不运行验证、不选资产、不映射ETF、不生成权重、不配置、不交易。",
                    "external validation research protocol",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/external-validation/execution-runs",
                    "返回 V11.2 H2 External Validation Execution Framework，按 V11.1 预注册窗口读取冻结风险证据并输出 passed/failed/inconclusive；不策略化、不配置、不优化、不交易。",
                    "H2 external validation execution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/external-validation/result-freeze",
                    "返回 V11.3 H2 External Validation Result Freeze，冻结 H2 外部验证最终解释：风险证据可见但稳定性不足，继续观察；不策略化、不配置、不优化、不交易。",
                    "H2 external validation result freeze",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/research-phase/closure",
                    "返回 V11.4 Research Phase Closure，冻结 V6-V11 研究阶段最终架构：风险诊断仅观察用，机会/配置/交易未就绪；不新增研究层、不策略化、不配置、不交易。",
                    "research phase closure",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-boundary/research-to-implementation",
                    "返回 V12.1 Research-to-Implementation Boundary Design，定义冻结研究结果进入实现层之前的隔离边界：只允许只读观察/研究治理候选，机会、配置、资产、组合、执行仍隔离；不生成策略、权重、配置或交易。",
                    "research-to-implementation boundary",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/evidence-specification",
                    "返回 V12.2 Implementation Readiness Evidence Specification，定义未来进入实现阶段前必须满足的证据标准；不评价证据、不生成策略、资产、ETF、权重、配置或交易。",
                    "implementation readiness evidence specification",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/evidence-audit",
                    "返回 V12.3 Implementation Readiness Evidence Audit Framework，定义未来 evidence package 审计框架；当前 package 未提交，所有组件保持 blocked，不评估收益、不生成策略、资产、ETF、权重、配置或交易。",
                    "implementation readiness evidence audit framework",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/evidence-submission-protocol",
                    "返回 V13.1 Research Component Evidence Submission Protocol，定义未来研究组件提交实现资格证据包的标准格式；当前不提交证据包，不生成策略、资产、ETF、权重、配置或交易。",
                    "research component evidence submission protocol",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/evidence-package-validator",
                    "返回 V13.2 Evidence Package Validation Engine，定义未来证据包自动校验能力；当前不接收真实证据包，状态为 invalid_not_submitted，不评估收益、不生成策略、资产、ETF、权重、配置或交易。",
                    "evidence package validation engine",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/invalid-evidence-example",
                    "返回 V13.3 Invalid Evidence Package Rejection Test，使用模拟不合格证据包验证校验引擎能拒绝缺字段和越界输出；不使用真实策略证据、不生成资产、ETF、权重、配置或交易。",
                    "invalid evidence package rejection example",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/governance-freeze",
                    "返回 V13.4 Implementation Readiness Governance Freeze，冻结 V12-V13 实现准入治理链；不提交真实证据、不生成策略、资产、ETF、权重、配置或交易。",
                    "implementation readiness governance freeze",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-evidence-package",
                    "返回 V14.1 Risk Diagnostic Layer Evidence Package Phase 0：提交风险诊断层单组件证据包，经过格式与边界校验，但 implementation_ready=false，不生成策略、资产、ETF、权重、配置或交易。",
                    "risk diagnostic evidence package",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-framework",
                    "返回 V14.2 Risk Diagnostic Shadow Observation Framework：定义无交易 shadow observation 事件记录、上下文快照和后验复盘框架；当前 shadow_status=planned、事件数 0、不可调仓、不可交易。",
                    "risk diagnostic shadow observation framework",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-log",
                    "返回 V14.3 Risk Diagnostic Shadow Observation Log Initialization：初始化 active 空观察日志；事件数 0、手动追加、自动触发关闭、不可调仓、不可交易。",
                    "risk diagnostic shadow observation log",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-review",
                    "返回 V14.4 Risk Diagnostic Shadow Observation Event Review Framework：定义未来影子事件的完整性、lineage、无交易合规和后验结果复核；当前 no_events_available，不自动判断风险、不交易。",
                    "risk diagnostic shadow observation review",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-manual-capture",
                    "返回 V14.5 Risk Diagnostic Shadow Event Manual Capture：人工事件文件录入能力状态，默认本次提交 0 事件；只允许 append-only、去重、source hash 和无交易校验。",
                    "risk diagnostic shadow manual event capture",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-quality-audit",
                    "返回 V14.6 Risk Diagnostic Shadow Event Quality Audit：检查未来人工事件的完整性、source hash、去重、后验复核字段和无交易边界；当前 no_events_available。",
                    "risk diagnostic shadow event quality audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-first-event-workflow",
                    "返回 V14.7 Risk Diagnostic Shadow Observation First Event Workflow：定义首个人工 shadow event 从人工 JSON、校验、质量审计队列到后验复核的完整流程；当前 ready_for_first_manual_event。",
                    "risk diagnostic shadow first event workflow",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-event-input-package",
                    "返回 V14.8 First Manual Shadow Event Submission Input Package：人工事件输入模板、JSON schema 和只校验不提交的 CLI；当前 event_submitted=false。",
                    "risk diagnostic shadow event input package",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/implementation-readiness/risk-diagnostic-shadow-evidence-dashboard",
                    "返回 V14.9 Shadow Evidence Accumulation Dashboard：只汇总事件数、待复核、已复核、误报/漏报和质量队列；不生成事件、不判断风险、不交易。",
                    "risk diagnostic shadow evidence dashboard",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-direction",
                    "返回 V15.0 主线收益策略重构方向声明：冻结 V12-V14 为治理/证据基础设施，V15+ 切回收益第一、回撤第二的策略回测主线；不回测、不配置、不交易。",
                    "v15 mainline outcome strategy rebase",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-backtest-dataset",
                    "返回 V15.1 收益导向回测数据集 manifest：定义宽基、行业、宏观、回撤和结构牛字段要求；不拉全量数据、不跑策略、不出仓位或交易信号。",
                    "v15 outcome backtest dataset manifest",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-dataset-materialization",
                    "返回 V15.2 回测数据落地覆盖率报告：只读本地缓存，记录 source/cache hash、缺失字段和时间安全要求；不跑策略、不出仓位或交易信号。",
                    "v15 outcome backtest dataset materialization status",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-macro-drawdown-backtest",
                    "返回 V15.3 宏观周期 + 回撤情境基准研究回测：对比现金、沪深300、上证指数和旧策略基线；仅研究回测，不生成交易信号、不接券商、不下单。",
                    "v15 macro drawdown regime baseline research backtest",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-macro-drawdown-robustness",
                    "返回 V15.4 参数邻域、交易成本和年度滚动样本外验证；明确历史阶段严格时点性仍未独立证实，不生成交易信号。",
                    "v15 macro drawdown robustness and walk-forward validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-point-in-time-phase-rebuild",
                    "返回 V15.5 严格时点阶段重建审计或缺口报告；当前不伪造已验证状态，不回测、不出仓位或交易信号。",
                    "v15 strict point-in-time phase reconstruction audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-late-cycle-overlay-manifest",
                    "返回 V15.5 高位估值与拥挤覆盖层六项特征的数据契约；只定义研究前置条件，不跑回测、不优化、不交易。",
                    "v15 late-cycle overlay data contract",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-point-in-time-snapshot-ledger",
                    "返回 V15.6 逐日期不可变源快照账本，区分历史快照 hash 与当前文件 hash；只记录证据缺口，不回测、不优化、不交易。",
                    "v15 immutable point-in-time source snapshot ledger",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-point-in-time-snapshot-ledger-status",
                    "返回 V15.6 快照账本覆盖统计与回测门禁；缺少真实历史快照时保持 backtest_allowed=false。",
                    "v15 point-in-time snapshot ledger status",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-daily-snapshot-capture",
                    "返回 V15.7 当日前向不可变快照状态、Manifest hash 和源覆盖；不回测、不生成仓位或交易信号。",
                    "v15 daily immutable snapshot capture status",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-forward-paper-decision",
                    "返回 V15.7 仅供前向观察的纸面决策记录；禁止实盘信号、标的、仓位、订单和券商连接。",
                    "v15 forward paper-only decision record",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-forward-observation-journal",
                    "返回 V15.8 append-only 前向观察日志状态、累计日期和待回填结果数量；不回测、不评价收益、不生成仓位或交易。",
                    "v15 append-only forward observation journal status",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-rebase/v15-forward-outcomes",
                    "返回 V15.9 沪深300 T+1/T+5/T+20 前向市场结果回填状态；不是策略收益，不回测、不出仓位或交易信号。",
                    "v15 forward benchmark outcome intake status",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/structural-bull-validation",
                    "返回 V3.5.3 结构性牛市专用风格轮动验证，限定 STRUCTURAL_BULL 样本，比较基线和风格偏好资产池的收益、风险和风格漂移；只读研究验证。",
                    "structural bull style rotation validation",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/structural-bull-failure-analysis",
                    "返回 V3.5.4 结构牛风格失败归因，拆分风格偏好跑赢/跑输样本并解释信号日可见条件差异；只读研究归因，不生成配置或交易信号。",
                    "structural bull style failure attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/historical-context",
                    "返回 V3.5.5 历史风格上下文特征，按历史日期重建行业扩散、主线持续性、拥挤风险和价格延伸代理；只读研究数据，不修改策略。",
                    "historical style context features",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/historical-context-coverage",
                    "返回 V3.5.5 历史风格上下文字段覆盖率审计，披露完整覆盖、缺失字段和数据安全边界。",
                    "historical style context coverage audit",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/style/structural-bull-context-attribution",
                    "返回 V3.5.6 结构牛风格上下文再归因，把历史风格上下文字段 join 回成功/失败样本，检验行业扩散、主题持续、拥挤和重叠度假设；只读研究归因。",
                    "structural bull style context re-attribution",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/strategy-backtests/{strategy_id}",
                    "返回新增策略回测结果，strategy_id 支持 defensive-dividend、industry-momentum、four-asset、max-drawdown-batch、all-weather、equal-weight-reversion-basic、equal-weight-reversion-guarded、free-cash-flow-trend-half、free-cash-flow-trend-full、free-cash-flow-drawdown-rebound、free-cash-flow-buy-hold-480092、free-cash-flow-chinext-dynamic、free-cash-flow-chinext-reversion、free-cash-flow-chinext-balanced-reversion、free-cash-flow-ma-deviation、free-cash-flow-dual-ma-crossover。",
                    "strategy backtest artifact",
                    params=[{"name": "strategy_id", "required": "true", "format": "path"}],
                    freshness="generated artifact",
                ),
            ],
        },
        {
            "name": "仓位风控回测",
            "description": "用历史 R2 动态仓位回放 510500 基准收益，评估风控仓位策略相对满仓基准的收益、回撤和 Alpha。",
            "endpoints": [
                _api_endpoint(
                    "GET",
                    "/api/shadow/current",
                    "返回 S1.1 仓位风控回测与 510500 基准的完整权益曲线、收益序列和 Alpha；收益口径优先使用 fund_daily pct_chg/pre_close。",
                    "shadow portfolio backtest",
                    freshness="generated artifact",
                ),
                _api_endpoint(
                    "GET",
                    "/api/shadow/regime-attribution",
                    "返回 S1.2 按牛熊状态拆解的收益、回撤、Alpha 拖累项和保护项。",
                    "regime performance attribution",
                    freshness="generated artifact",
                ),
            ],
        },
        {
            "name": "系统成果总览",
            "description": "系统冻结状态、完整成果和研究验证摘要。",
            "endpoints": [
                _api_endpoint("GET", "/api/system/snapshot", "系统边界、冻结文档、策略锁定和当前状态快照。", "system snapshot"),
                _api_endpoint(
                    "GET",
                    "/api/results/summary",
                    "页面使用的成果汇总，包括风控、组合、策略、执行和验证结论；compact=true 时省略回测长曲线用于首页提速。",
                    "results summary",
                    params=[{"name": "compact", "required": "false", "format": "boolean"}],
                ),
            ],
        },
    ]
    total_endpoints = sum(len(group["endpoints"]) for group in groups)
    return {
        "name": "MyInvestCycle API",
        "version": app.version,
        "status": "stable",
        "description": "A股牛熊周期识别、风险控制、组合配置、策略路由与执行模拟的只读接口目录。",
        "base_url": "http://127.0.0.1:8021",
        "web_dashboard": "/",
        "docs": {
            "interactive": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
        "recommended_entrypoints": [
            {"path": "/api", "description": "先看接口目录。"},
            {"path": "/api/results/summary", "description": "读取系统全部成果汇总。"},
            {"path": "/api/system/snapshot", "description": "读取系统冻结边界与稳定状态。"},
            {"path": "/", "description": "查看宏观周期总览。"},
            {"path": "/strategies", "description": "查看策略回测频道。"},
            {"path": "/validation", "description": "查看验证归因频道。"},
            {"path": "/v15-formal-evaluation", "description": "查看V15全收益与15bp成本正式评价。"},
            {"path": "/api/regime/current", "description": "读取当前牛熊状态与四维评分。"},
            {"path": "/api/regime/cycle/track", "description": "读取后市展望的位置和概率。"},
            {"path": "/api/macro/context-history", "description": "读取 V5.7 release-date 安全的历史宏观上下文。"},
            {"path": "/api/meta-edge/current", "description": "读取系统内部矛盾信号。"},
            {"path": "/api/style/current", "description": "读取风格评分与 ETF 候选池。"},
            {"path": "/api/style/rotation-signal", "description": "读取 ETF 轮动信号与目标权重建议。"},
            {"path": "/strategy/etf-rotation", "description": "查看 ETF 轮动策略回测、图表和调仓历史入口。"},
            {"path": "/api/style/rotation-backtest", "description": "读取 ETF 轮动 Alpha 验证结果。"},
            {"path": "/strategy/macro-style", "description": "查看 Macro-Style-ETF 分层策略回测、图表和调仓历史入口。"},
            {"path": "/api/style/macro-style-etf-backtest", "description": "读取 Macro-Style-ETF 分层组合回测结果。"},
            {"path": "/api/alpha/portfolio-risk-validation", "description": "读取 V3.4.3 Alpha 组合风险控制验证。"},
            {"path": "/api/alpha/robustness-validation", "description": "读取 V3.4.4 Alpha 滚动稳健性和风格归因验证。"},
            {"path": "/api/alpha/residual-alpha-analysis", "description": "读取 V3.4.5 残差 Alpha 与因子中性化归因。"},
            {"path": "/api/style/allocation-snapshot", "description": "读取 V3.5.1 宏观感知风格偏好快照。"},
            {"path": "/api/style/validation", "description": "读取 V3.5.2 风格偏好验证与归因。"},
            {"path": "/api/style/incremental-analysis", "description": "读取 V3.5.7 风格偏好增量信息检验。"},
            {"path": "/api/allocation/policy", "description": "读取 V4.1 Beta 风险预算约束层。"},
            {"path": "/api/allocation/policy-validation", "description": "读取 V4.2 风险预算历史重放与矛盾审计。"},
            {"path": "/api/allocation/opportunity-risk", "description": "读取 V4.3 机会状态与风险状态二维拆分。"},
            {"path": "/api/allocation/opportunity-risk-policy", "description": "读取 V4.4 机会-风险到定性政策模式的映射验证。"},
            {"path": "/api/allocation/policy-effectiveness", "description": "读取 V4.5 政策模式解释力与反事实矛盾审计。"},
            {"path": "/api/allocation/market-phase", "description": "读取 V4.6 市场阶段第三维分类。"},
            {"path": "/api/allocation/phase-effectiveness", "description": "读取 V4.7 市场阶段解释力与错误案例审计。"},
            {"path": "/api/allocation/exposure-simulation", "description": "读取 V5.1 定性暴露等级模拟与历史矛盾审计。"},
            {"path": "/api/allocation/exposure-effectiveness", "description": "读取 V5.2 定性暴露等级有效性与有序性审计。"},
            {"path": "/api/allocation/exposure-context-analysis", "description": "读取 V5.3 BALANCED 暴露桶上下文拆解审计。"},
            {"path": "/api/allocation/balanced-context-audit", "description": "读取 V5.4 BALANCED 候选子状态质量审计。"},
            {"path": "/api/allocation/balanced-candidate-failure-analysis", "description": "读取 V5.5 BALANCED 候选失败与机会错失归因。"},
            {"path": "/api/allocation/exposure-numeric-context", "description": "读取 V5.6 暴露重放数值上下文和时间安全覆盖率。"},
            {"path": "/api/allocation/macro-enhanced-context-analysis", "description": "读取 V5.8 宏观增强 BALANCED 候选重新归因。"},
            {"path": "/api/allocation/exposure-context-state-audit", "description": "读取 V5.9 BALANCED 上下文状态模型设计审计。"},
            {"path": "/api/allocation/exposure-gradient-analysis", "description": "读取 V5.10 BALANCED 连续风险/机会梯度审计。"},
            {"path": "/api/allocation/risk-gradient-robustness", "description": "读取 V5.11 风险梯度分阶段稳健性审计。"},
            {"path": "/api/allocation/risk-gradient-condition-analysis", "description": "读取 V5.12 风险梯度条件有效性审计。"},
            {"path": "/api/allocation/risk-gradient-candidate-rules", "description": "读取 V5.13 风险梯度最小候选规则审计。"},
            {"path": "/api/allocation/exposure-policy-validation", "description": "读取 V6.1 自适应暴露策略诊断叠加验证。"},
            {"path": "/api/allocation/exposure-decision-audit", "description": "读取 V6.2 暴露决策上下文设计审计。"},
            {"path": "/api/allocation/exposure-context-score-audit", "description": "读取 V6.3 连续暴露上下文评分审计。"},
            {"path": "/api/allocation/protection-score-validation", "description": "读取 V6.4 保护分稳健性与条件验证。"},
            {"path": "/api/allocation/two-axis-context-validation", "description": "读取 V6.5 风险-机会双轴环境验证。"},
            {"path": "/api/allocation/context-information-attribution", "description": "读取 V6.6 上下文信息层价值归因。"},
            {"path": "/api/opportunity/research-foundation", "description": "读取 V7.1 机会研究基础层：资产池、研究代理、覆盖率和只读边界。"},
            {"path": "/api/opportunity/context-features", "description": "读取 V7.2 机会研究特征层：动量、相对强弱、趋势、风险和结构字段。"},
            {"path": "/api/opportunity/feature-validation", "description": "读取 V7.3 机会特征有效性审计：IC、proxy/ETF 分离和环境分层。"},
            {"path": "/api/opportunity/feature-attribution", "description": "读取 V7.4 机会特征归因与稳定性审计：保留/观察/暂弃标签和环境一致性。"},
            {"path": "/api/opportunity/v7-architecture", "description": "读取 V7.5 机会研究层冻结摘要：保留层、拒绝项和不可评分/排名/配置/交易边界。"},
            {"path": "/api/decision/research-context", "description": "读取 V8.1 研究决策整合语境：V6 风险上下文 + V7 机会研究，只读且不输出资产/排名/配置/交易。"},
            {"path": "/api/decision/scenario-audit", "description": "读取 V8.2 历史情景解释审计：固定场景一致性、切换稳定、矛盾样本和覆盖缺口。"},
            {"path": "/api/decision/contradiction-attribution", "description": "读取 V8.3 矛盾场景归因：解释研究语境失败原因，不改规则、不输出策略。"},
            {"path": "/api/decision/v8-architecture", "description": "读取 V8.4 研究决策架构冻结摘要：V8.1-V8.3 保留层、拒绝项和不可策略化边界。"},
            {"path": "/api/allocation-research/architecture", "description": "读取 V9.1 配置研究架构基础：输入、未来证据要求、禁止输出和未就绪状态。"},
            {"path": "/api/allocation-research/hypotheses", "description": "读取 V9.2 配置研究假设框架：仅列出未验证假设和验证要求，不输出资产、ETF、权重、回测或交易。"},
            {"path": "/api/allocation-research/validation-plan", "description": "读取 V9.3 配置研究验证计划：只设计样本外、回撤、矛盾、稳定性和防过拟合验证方法，不执行验证。"},
            {"path": "/api/allocation-research/experiment-templates", "description": "读取 V9.4 配置研究实验模板：只定义预声明比较方法、评价标准和失败标准，不运行实验。"},
            {"path": "/api/allocation-research/experiment-results", "description": "读取 V9.5 Phase 0 研究实验执行结果：只检查预声明模板纪律，不产生可投资输出。"},
            {"path": "/api/allocation-research/experiment-phase1-validation", "description": "读取 V9.6 Phase 1 研究实验验证结果：含输入哈希和研究状态，仍不配置、不交易。"},
            {"path": "/api/allocation-research/research-candidate-gate", "description": "读取 V9.7 研究阶段门禁审计：只判断继续研究、冻结或暂拒，仍不策略化、不配置、不交易。"},
            {"path": "/api/allocation-research/research-candidate-deep-validation", "description": "读取 V9.8 研究候选深度验证：只深化 H2/H4 的研究证据，不策略化、不配置、不交易。"},
            {"path": "/api/allocation-research/evidence-freeze", "description": "读取 V9.9 配置研究证据冻结：固化 H1-H4 状态和决策边界，不进入策略或配置。"},
            {"path": "/api/allocation-research/execution-runs", "description": "读取 V10.1 配置研究执行记录：只执行冻结研究实验流程，不生成资产、权重、配置或交易。"},
            {"path": "/api/allocation-research/result-review", "description": "读取 V10.2 配置研究结果审查：只审查 H2/H4 执行结果，不策略化、不配置、不交易。"},
            {"path": "/api/allocation-research/final-boundary", "description": "读取 V10.3 配置研究最终边界：H2 只允许外部验证，H4 仅研究治理，H1/H3 冻结；不策略化、不配置、不交易。"},
            {"path": "/api/external-validation/protocol", "description": "读取 V11.1 H2 外部验证协议：只定义预注册验证流程、失败标准和停止条件，不运行验证、不配置、不交易。"},
            {"path": "/api/external-validation/execution-runs", "description": "读取 V11.2 H2 外部验证执行结果：只输出窗口级 passed/failed/inconclusive，不策略化、不配置、不交易。"},
            {"path": "/api/external-validation/result-freeze", "description": "读取 V11.3 H2 外部验证结果冻结：结论为不确定、继续观察，不策略化、不配置、不交易。"},
            {"path": "/api/research-phase/closure", "description": "读取 V11.4 研究阶段关闭与最终架构冻结：V6-V11 收口，风险仅观察用，机会/配置/交易未就绪。"},
            {"path": "/api/implementation-boundary/research-to-implementation", "description": "读取 V12.1 研究到实现隔离边界：定义可观察候选、隔离项和进入实现前的额外验证要求。"},
            {"path": "/api/implementation-readiness/evidence-specification", "description": "读取 V12.2 实现就绪证据标准：定义未来允许进入实现前必须满足的证据，不评价证据、不输出策略。"},
            {"path": "/api/implementation-readiness/evidence-audit", "description": "读取 V12.3 实现证据审计框架：定义未来 evidence package 审计方式；当前未提交证据，所有组件 blocked。"},
            {"path": "/api/implementation-readiness/evidence-submission-protocol", "description": "读取 V13.1 证据包提交协议：定义未来研究组件如何提交实现资格证据包；当前不提交证据。"},
            {"path": "/api/implementation-readiness/evidence-package-validator", "description": "读取 V13.2 证据包校验引擎：定义未来 evidence package 的格式和边界自动校验；当前不接收真实证据。"},
            {"path": "/api/implementation-readiness/invalid-evidence-example", "description": "读取 V13.3 不合格证据包拒绝测试：用模拟缺陷包证明 validator 会拒绝越界输入。"},
            {"path": "/api/implementation-readiness/governance-freeze", "description": "读取 V13.4 实现准入治理冻结：冻结 V12-V13 治理链，仍无真实候选或实现输出。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-evidence-package", "description": "读取 V14.1 风险诊断层证据包：单组件证据已提交，但仍 blocked，不输出策略、权重、配置或交易。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-framework", "description": "读取 V14.2 风险诊断影子观察框架：只定义无交易观察日志和后验复盘字段，当前未产生事件。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-log", "description": "读取 V14.3 风险诊断影子观察日志：active 空日志，事件数 0，仅允许未来手动追加无交易观察。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-review", "description": "读取 V14.4 风险诊断影子事件复核框架：当前无事件可复核，不自动判断风险、不配置不交易。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-manual-capture", "description": "读取 V14.5 风险诊断人工事件录入能力：默认不提交事件，只定义手工事件文件追加、去重和无交易校验。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-quality-audit", "description": "读取 V14.6 风险诊断事件质量审计：当前无事件可审计，未来只检查人工事件质量，不自动决策不交易。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-first-event-workflow", "description": "读取 V14.7 风险诊断首个人工事件流程：当前可准备首个事件，但不自动扫描、不生成事件、不交易。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-event-input-package", "description": "读取 V14.8 风险诊断人工事件输入包：模板和校验 CLI 已就绪，当前未提交事件。"},
            {"path": "/api/implementation-readiness/risk-diagnostic-shadow-evidence-dashboard", "description": "读取 V14.9 风险诊断影子证据积累看板：当前等待人工事件，事件/复核/误报/漏报/质量队列均为 0。"},
            {"path": "/api/strategy-rebase/v15-direction", "description": "读取 V15.0 主线收益策略重构方向声明：V12-V14 冻结为基础设施，V15+ 回到收益和回撤导向。"},
            {"path": "/api/strategy-rebase/v15-backtest-dataset", "description": "读取 V15.1 收益导向回测数据集 manifest：只定义未来数据底座，不回测、不配置、不交易。"},
            {"path": "/api/strategy-rebase/v15-dataset-materialization", "description": "读取 V15.2 回测数据落地状态：只读本地缓存，报告覆盖率和 hash，不回测、不配置、不交易。"},
            {"path": "/api/strategy-rebase/v15-macro-drawdown-backtest", "description": "读取 V15.3 宏观周期 + 回撤情境基准研究回测：对比现金、沪深300、上证指数和旧策略基线；不生成交易信号。"},
            {"path": "/api/strategy-rebase/v15-macro-drawdown-robustness", "description": "读取 V15.4 参数稳健性、成本敏感性与年度滚动样本外验证；不生成交易信号。"},
            {"path": "/api/strategy-rebase/v15-point-in-time-phase-rebuild", "description": "读取 V15.5 严格时点阶段重建审计或缺口报告；不伪造验证通过，不回测不交易。"},
            {"path": "/api/strategy-rebase/v15-late-cycle-overlay-manifest", "description": "读取 V15.5 高位估值与拥挤覆盖层六项特征数据契约；不跑回测、不优化、不交易。"},
            {"path": "/api/strategy-rebase/v15-point-in-time-snapshot-ledger", "description": "读取 V15.6 逐日期不可变源快照账本；严格区分历史快照 hash 与当前文件 hash，不回测不交易。"},
            {"path": "/api/strategy-rebase/v15-point-in-time-snapshot-ledger-status", "description": "读取 V15.6 快照账本覆盖和回测门禁状态；真实 lineage 不完整时禁止回测。"},
            {"path": "/api/strategy-rebase/v15-daily-snapshot-capture", "description": "读取 V15.7 当日前向不可变快照状态、Manifest hash 和源覆盖；不回测不交易。"},
            {"path": "/api/strategy-rebase/v15-forward-paper-decision", "description": "读取 V15.7 仅供未来观察的纸面决策记录；不生成标的、仓位、买卖或订单。"},
            {"path": "/api/strategy-rebase/v15-forward-observation-journal", "description": "读取 V15.8 append-only 前向观察日志状态；只累计真实前向记录，不回测、不评价收益、不交易。"},
            {"path": "/api/strategy-rebase/v15-forward-outcomes", "description": "读取 V15.9 沪深300前向市场结果回填状态；只记录 benchmark outcome，不代表策略收益或交易信号。"},
            {"path": "/api/style/structural-bull-validation", "description": "读取 V3.5.3 结构性牛市风格轮动验证。"},
            {"path": "/api/style/structural-bull-failure-analysis", "description": "读取 V3.5.4 结构牛风格失败归因。"},
            {"path": "/api/style/historical-context", "description": "读取 V3.5.5 历史风格上下文特征。"},
            {"path": "/api/style/historical-context-coverage", "description": "读取 V3.5.5 历史风格上下文覆盖审计。"},
            {"path": "/api/style/structural-bull-context-attribution", "description": "读取 V3.5.6 结构牛风格上下文再归因。"},
            {"path": "/strategy/defensive-dividend", "description": "查看红利低波 + 现金代理防守策略。"},
            {"path": "/strategy/industry-momentum", "description": "查看行业 ETF 动量轮动 + 511880 空仓机制策略。"},
            {"path": "/strategy/four-asset", "description": "查看股 / 债 / 金 / 现金四资产轮动策略。"},
            {"path": "/strategy/max-drawdown-batch", "description": "查看最大回撤分批买入策略。"},
            {"path": "/strategy/all-weather", "description": "查看 All Weather Portfolio（A股 ETF 全天候组合）。"},
            {"path": "/strategy/equal-weight-reversion-basic", "description": "查看四 ETF 等权均线回归基础版。"},
            {"path": "/strategy/equal-weight-reversion-guarded", "description": "查看四 ETF 等权均线回归风控版。"},
            {"path": "/strategy/free-cash-flow-trend-half", "description": "查看自由现金流趋势通道半仓防守版。"},
            {"path": "/strategy/free-cash-flow-trend-full", "description": "查看自由现金流趋势通道满仓/空仓版。"},
            {"path": "/strategy/free-cash-flow-drawdown-rebound", "description": "查看自由现金流回撤反弹五阈值策略。"},
            {"path": "/strategy/free-cash-flow-buy-hold-480092", "description": "查看自由现金流R满仓持有与全收益指数对比。"},
            {"path": "/strategy/free-cash-flow-chinext-dynamic", "description": "查看自由现金流R/创业板R动态满仓策略。"},
            {"path": "/strategy/free-cash-flow-chinext-reversion", "description": "查看自由现金流R/创业板R相对回归策略。"},
            {"path": "/strategy/free-cash-flow-chinext-balanced-reversion", "description": "查看自由现金流R/创业板R平衡回归策略。"},
            {"path": "/strategy/free-cash-flow-ma-deviation", "description": "查看自由现金流R均线偏离策略与参数扫描。"},
            {"path": "/strategy/free-cash-flow-dual-ma-crossover", "description": "查看自由现金流R双均线金叉死叉策略与参数扫描。"},
            {"path": "/api/shadow/current", "description": "读取仓位风控回测与 510500 基准评估。"},
            {"path": "/api/v2/full-cycle-backtest", "description": "读取 V2.6.3 2015 起完整窗口 walk-forward 回测、基准对比和阶段归因。"},
        ],
        "safety": {
            "read_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_real_orders": True,
            "no_broker_connection": True,
            "simulation_only": True,
        },
        "groups": groups,
        "total_endpoints": total_endpoints,
    }


@app.get("/api")
def api_catalog() -> dict:
    return _api_catalog_payload()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return FileResponse(ROOT_DIR / "web" / "templates" / "dashboard.html")


@app.get("/v2", response_class=HTMLResponse)
def v2_dashboard_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "v2_dashboard.html")


@app.get("/v2-validation", response_class=HTMLResponse)
def v2_validation_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "v2_validation.html")


@app.get("/risk-execution", response_class=HTMLResponse)
def risk_execution_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "risk_execution.html")


@app.get("/strategies", response_class=HTMLResponse)
def strategies_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategies.html")


@app.get("/validation", response_class=HTMLResponse)
def validation_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "validation.html")


@app.get("/v15-formal-evaluation", response_class=HTMLResponse)
def v15_formal_evaluation_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "v15_formal_evaluation.html")


@app.get("/strategy/etf-rotation", response_class=HTMLResponse)
def etf_rotation_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_etf_rotation.html")


@app.get("/strategy/macro-style", response_class=HTMLResponse)
def macro_style_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_macro_style.html")


@app.get("/strategy/defensive-dividend", response_class=HTMLResponse)
def defensive_dividend_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/industry-momentum", response_class=HTMLResponse)
def industry_momentum_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/four-asset", response_class=HTMLResponse)
def four_asset_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/max-drawdown-batch", response_class=HTMLResponse)
def max_drawdown_batch_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/all-weather", response_class=HTMLResponse)
def all_weather_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/equal-weight-reversion-basic", response_class=HTMLResponse)
def equal_weight_reversion_basic_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/equal-weight-reversion-guarded", response_class=HTMLResponse)
def equal_weight_reversion_guarded_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-trend-half", response_class=HTMLResponse)
def free_cash_flow_trend_half_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-trend-full", response_class=HTMLResponse)
def free_cash_flow_trend_full_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-drawdown-rebound", response_class=HTMLResponse)
def free_cash_flow_drawdown_rebound_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-buy-hold-480092", response_class=HTMLResponse)
def free_cash_flow_buy_hold_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-chinext-dynamic", response_class=HTMLResponse)
def free_cash_flow_chinext_dynamic_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-chinext-reversion", response_class=HTMLResponse)
def free_cash_flow_chinext_reversion_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-chinext-balanced-reversion", response_class=HTMLResponse)
def free_cash_flow_chinext_balanced_reversion_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-ma-deviation", response_class=HTMLResponse)
def free_cash_flow_ma_deviation_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/strategy/free-cash-flow-dual-ma-crossover", response_class=HTMLResponse)
def free_cash_flow_dual_ma_crossover_strategy_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "strategy_generic.html")


@app.get("/rotation-history", response_class=HTMLResponse)
def rotation_history_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "rotation_history.html")


@app.get("/macro-style-history", response_class=HTMLResponse)
def macro_style_history_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "macro_style_history.html")


@app.get("/cycle-track", response_class=HTMLResponse)
def cycle_track_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "cycle_track.html")


@app.get("/cycle-observation", response_class=HTMLResponse)
def cycle_observation_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "cycle_observation.html")


@app.get("/api-docs", response_class=HTMLResponse)
def api_docs_page():
    return FileResponse(ROOT_DIR / "web" / "templates" / "api_docs.html")


@app.get("/api/regime/current")
def regime_current() -> dict:
    try:
        return _current_regime_payload()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/features/latest")
def features_latest() -> dict:
    payload = regime_current()
    return {
        "as_of": payload["as_of"],
        "trend_score": payload["trend_score"],
        "breadth_score": payload["breadth_score"],
        "liquidity_score": payload["liquidity_score"],
        "volatility_score": payload["volatility_score"],
        "sub_scores": payload["sub_scores"],
    }


@app.get("/api/regime/explain")
def regime_explain() -> dict:
    return explain_regime(regime_current())


@app.get("/api/regime/cycle")
def regime_cycle() -> dict:
    try:
        index_df = _load_cycle_index(_today_text())
        return detect_major_cycles(index_df)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/regime/cycle/track")
def regime_cycle_track() -> dict:
    try:
        index_df = _load_cycle_index(_today_text())
        return detect_current_cycle_track(index_df)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/regime/score-history")
def regime_score_history(
    fill_tail: bool = Query(False, description="Whether to compute missing tail sessions after cached history."),
) -> dict:
    try:
        index_df = _load_cycle_index(_today_text())
        if index_df.empty:
            raise HTTPException(status_code=503, detail="No index data available.")
        cycle_payload = detect_major_cycles(index_df)
        current_cycle = cycle_payload.get("current_cycle") or {}
        start_date = str(current_cycle.get("start_date") or index_df["trade_date"].iloc[-1])
        end_date = str(cycle_payload.get("as_of") or index_df["trade_date"].iloc[-1])
        cycle_index = index_df[
            (index_df["trade_date"] >= start_date) & (index_df["trade_date"] <= end_date)
        ].copy()
        if cycle_index.empty:
            raise HTTPException(status_code=503, detail="No index data available for current cycle.")

        close_by_date = dict(zip(cycle_index["trade_date"].astype(str), cycle_index["close"]))
        cached_items, cache_meta = _cached_score_history_items(start_date, end_date, close_by_date)
        cached_dates = {item["as_of"] for item in cached_items}
        cycle_dates = cycle_index["trade_date"].astype(str).tolist()
        missing_dates = [trade_date for trade_date in cycle_dates if trade_date not in cached_dates]
        dynamic_items = _dynamic_score_history_items(missing_dates, index_df) if fill_tail and missing_dates else []
        items = sorted([*cached_items, *dynamic_items], key=lambda item: item["as_of"])
        if not items:
            raise HTTPException(status_code=503, detail="No score history items available.")

        return {
            "as_of": end_date,
            "start_date": start_date,
            "cycle": current_cycle,
            "source": {
                **cache_meta,
                "dynamic_tail_count": len(dynamic_items),
                "missing_dates": [] if fill_tail else missing_dates,
                "missing_dates_filled": missing_dates if fill_tail else [],
                "history_end": items[-1]["as_of"],
                "latest_index": {
                    "as_of": end_date,
                    "close": _float_or_none(close_by_date.get(end_date), 4),
                },
            },
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/portfolio/current")
def portfolio_current() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        return {
            "as_of": snapshot["current"]["as_of"],
            "input": snapshot["risk_signal"],
            "risk_decision": snapshot["risk_decision"],
            "portfolio": snapshot["portfolio_allocation"],
            "strategy_route": snapshot["strategy_route"],
            "policy": _portfolio_policy_summary(snapshot["portfolio_policy"]),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/strategy/current")
def strategy_current() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        return {
            "as_of": snapshot["current"]["as_of"],
            "portfolio": snapshot["portfolio_allocation"],
            "strategy_route": snapshot["strategy_route"],
            "execution": snapshot["execution"],
            "policy": _strategy_policy_summary(snapshot["strategy_policy"]),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/execution/current")
def execution_current() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        return {
            "as_of": snapshot["current"]["as_of"],
            "strategy_route": snapshot["strategy_route"],
            "execution": snapshot["execution"],
            "policy": _execution_policy_summary(snapshot["execution_policy"]),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/meta-edge/current")
def meta_edge_current() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        return _meta_edge_payload(snapshot)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/style/current")
def style_current() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        return _style_rotation_payload(snapshot)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/macro/data-status")
def macro_data_status(
    start_date: str = Query("20240101", description="Observation start date, YYYYMMDD."),
    end_date: str | None = Query(None, description="Observation end date, YYYYMMDD. Defaults to today."),
    decision_date: str | None = Query(None, description="Decision date for future-leakage checks, YYYYMMDD."),
) -> dict:
    resolved_end = end_date or _today_text()
    resolved_decision = decision_date or resolved_end
    records_by_indicator = load_macro_indicators(DEFAULT_MACRO_INDICATORS, start_date, resolved_end)
    audit = audit_macro_records(
        records_by_indicator,
        required_indicators=DEFAULT_MACRO_INDICATORS,
        decision_date=resolved_decision,
    )
    return {
        "engine": "V2.1 Macro Data Foundation",
        "registry": registry_as_dict(),
        "audit": audit,
        "requested_range": {
            "start_date": start_date,
            "end_date": resolved_end,
            "decision_date": resolved_decision,
        },
        "constraints": {
            "no_macro_score": True,
            "no_macro_state": True,
            "no_bull_bear_judgement": True,
            "no_position_sizing": True,
            "no_etf_allocation": True,
            "no_backtest": True,
        },
    }


@app.get("/api/macro/current")
def macro_current(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    start_date: str = Query("20200101", description="Macro cache observation start date, YYYYMMDD."),
) -> dict:
    return build_macro_cycle_snapshot(date_text or _today_text(), start_date=start_date)


@app.get("/api/macro/context-history")
def macro_context_history() -> dict:
    payload = _read_macro_context_history_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Macro context history artifact missing; run scripts/build_macro_context_history.py first.",
        )
    return payload


@app.get("/api/structure/current")
def structure_current(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    start_date: str = Query("20150101", description="Index history start date, YYYYMMDD."),
    history_sample_size: int = Query(30, ge=0, le=100, description="Breadth history sample size."),
    cache_only: bool = Query(False, description="Use local cache only for breadth data."),
) -> dict:
    return build_structure_snapshot(
        date_text or _today_text(),
        start_date=start_date,
        history_sample_size=history_sample_size,
        cache_only=cache_only,
    )


@app.get("/api/industry/opportunity")
def industry_opportunity(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    start_date: str = Query("20240101", description="Industry history start date, YYYYMMDD."),
    cache_only: bool = Query(True, description="Use local cache only for Web/API reads."),
) -> dict:
    return build_industry_opportunity_snapshot(
        date_text or _today_text(),
        start_date=start_date,
        cache_only=cache_only,
    )


@app.get("/api/structural-bull/current")
def structural_bull_current(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    cache_only: bool = Query(True, description="Use local cache only for Web/API reads."),
) -> dict:
    return build_structural_bull_snapshot(
        date_text or _today_text(),
        cache_only=cache_only,
    )


@app.get("/api/theme-risk/current")
def theme_risk_current(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    start_date: str = Query("20240101", description="Theme history start date, YYYYMMDD."),
    cache_only: bool = Query(True, description="Use local cache only for Web/API reads."),
) -> dict:
    return build_theme_risk_snapshot(
        date_text or _today_text(),
        start_date=start_date,
        cache_only=cache_only,
    )


@app.get("/api/allocation/intent")
def allocation_intent(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    cache_only: bool = Query(True, description="Use local cache only for Web/API reads."),
) -> dict:
    return build_allocation_intent_snapshot(
        date_text or _today_text(),
        cache_only=cache_only,
    )


@app.get("/api/allocation/trace")
def allocation_trace(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    cache_only: bool = Query(True, description="Use local cache only for Web/API reads."),
) -> dict:
    return build_allocation_trace_snapshot(
        date_text or _today_text(),
        cache_only=cache_only,
    )


@app.get("/api/v2/overview")
def v2_overview(
    date_text: str | None = Query(None, alias="date", description="Decision date, YYYYMMDD. Defaults to today."),
    cache_only: bool = Query(True, description="Use local cache only for Web/API reads."),
) -> dict:
    requested_date = date_text or _today_text()
    macro = build_macro_cycle_snapshot(requested_date, start_date="20240101")
    structure = build_structure_snapshot(
        requested_date,
        start_date="20150101",
        history_sample_size=30,
        cache_only=cache_only,
    )
    industry = build_industry_opportunity_snapshot(
        requested_date,
        start_date="20240101",
        cache_only=cache_only,
    )
    structural = build_structural_bull_snapshot(
        requested_date,
        macro_payload=macro,
        structure_payload=structure,
        industry_payload=industry,
        cache_only=cache_only,
    )
    theme_risk = build_theme_risk_snapshot(
        requested_date,
        industry_payload=industry,
        start_date="20240101",
        cache_only=cache_only,
    )
    allocation = build_allocation_intent_snapshot(
        requested_date,
        structural_payload=structural,
        theme_risk_payload=theme_risk,
        cache_only=cache_only,
    )
    trace = build_allocation_trace_snapshot(
        requested_date,
        allocation_payload=allocation,
        cache_only=cache_only,
    )
    return {
        "engine": "V2.4.3 V2 Research Dashboard Overview",
        "requested_as_of": normalize_trade_date(requested_date),
        "as_of": trace.get("as_of") or allocation.get("as_of"),
        "modules": {
            "macro": macro,
            "market_structure": structure,
            "industry_opportunity": industry,
            "structural_bull": structural,
            "theme_risk": theme_risk,
            "allocation_intent": allocation,
            "decision_trace": trace,
        },
        "constraints": {
            "read_only": True,
            "does_not_change_engine_outputs": True,
            "no_etf": True,
            "no_single_stock": True,
            "no_trade": True,
            "no_order": True,
            "no_backtest": True,
        },
    }


@app.get("/api/v2/backtest")
def v2_allocation_backtest() -> dict:
    payload = _read_v2_allocation_backtest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V2 allocation backtest artifact missing; run scripts/run_v2_allocation_backtest.py first.",
        )
    return payload


@app.get("/api/v2/policy-sensitivity")
def v2_policy_sensitivity() -> dict:
    payload = _read_v2_policy_sensitivity_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V2 policy sensitivity artifact missing; run scripts/run_v2_policy_sensitivity.py first.",
        )
    return payload


@app.get("/api/v2/structural-policy")
def v2_structural_policy() -> dict:
    payload = _read_structural_bull_policy_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Structural bull policy analysis artifact missing; run scripts/run_structural_policy_analysis.py first.",
        )
    return payload


@app.get("/api/v2/full-cycle-validation")
def v2_full_cycle_validation() -> dict:
    payload = _read_v2_full_cycle_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V2 full-cycle validation artifact missing; run scripts/run_v2_full_cycle_validation.py first.",
        )
    return payload


@app.get("/api/v2/history-expansion")
def v2_history_expansion() -> dict:
    payload = _read_history_expansion_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V2 history expansion artifact missing; run scripts/run_history_expansion.py first.",
        )
    return payload


@app.get("/api/v2/full-cycle-backtest")
def v2_full_cycle_backtest() -> dict:
    payload = _read_v2_full_cycle_backtest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V2 full-cycle backtest artifact missing; run scripts/run_v2_full_cycle_backtest.py first.",
        )
    return payload


@app.get("/api/style/rotation-signal")
def style_rotation_signal() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        style_rotation = _style_rotation_payload(snapshot)
        return _etf_rotation_signal_payload(style_rotation)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/style/rotation-backtest")
def style_rotation_backtest() -> dict:
    payload = _read_etf_rotation_backtest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="ETF rotation backtest artifact missing; run scripts/run_etf_rotation_backtest.py first.",
        )
    return payload


@app.get("/api/style/macro-style-etf-backtest")
def macro_style_etf_backtest() -> dict:
    payload = _read_macro_style_etf_backtest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Macro-Style-ETF backtest artifact missing; run scripts/run_macro_style_etf_backtest.py first.",
        )
    return payload


@app.get("/api/alpha/portfolio-risk-validation")
def alpha_portfolio_risk_validation() -> dict:
    payload = _read_alpha_portfolio_risk_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Alpha portfolio risk validation artifact missing; run scripts/run_alpha_portfolio_risk_control.py first.",
        )
    return payload


@app.get("/api/alpha/robustness-validation")
def alpha_robustness_validation() -> dict:
    payload = _read_alpha_robustness_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Alpha robustness validation artifact missing; run scripts/run_alpha_robustness_validation.py first.",
        )
    return payload


@app.get("/api/alpha/residual-alpha-analysis")
def residual_alpha_analysis() -> dict:
    payload = _read_residual_alpha_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Residual alpha analysis artifact missing; run scripts/run_residual_alpha_analysis.py first.",
        )
    return payload


@app.get("/api/style/allocation-snapshot")
def style_allocation_snapshot() -> dict:
    payload = _read_style_allocation_snapshot_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Style allocation snapshot artifact missing; run scripts/run_style_allocation_snapshot.py first.",
        )
    return payload


@app.get("/api/style/validation")
def style_validation() -> dict:
    payload = _read_style_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Style validation artifact missing; run scripts/run_style_validation.py first.",
        )
    return payload


@app.get("/api/style/incremental-analysis")
def style_incremental_analysis() -> dict:
    payload = _read_style_incremental_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Style incremental analysis artifact missing; run scripts/run_style_incremental_analysis.py first.",
        )
    return payload


@app.get("/api/allocation/policy")
def allocation_policy_snapshot() -> dict:
    payload = _read_allocation_policy_snapshot_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation policy snapshot artifact missing; run scripts/run_allocation_policy_snapshot.py first.",
        )
    return payload


@app.get("/api/allocation/policy-validation")
def allocation_policy_validation() -> dict:
    payload = _read_allocation_policy_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation policy validation artifact missing; run scripts/run_policy_validation.py first.",
        )
    return payload


@app.get("/api/allocation/opportunity-risk")
def opportunity_risk_snapshot() -> dict:
    payload = _read_opportunity_risk_snapshot_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity/risk snapshot artifact missing; run scripts/run_opportunity_risk_snapshot.py first.",
        )
    return payload


@app.get("/api/allocation/opportunity-risk-policy")
def opportunity_risk_policy() -> dict:
    payload = _read_opportunity_risk_policy_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity/risk policy artifact missing; run scripts/run_opportunity_risk_policy.py first.",
        )
    return payload


@app.get("/api/allocation/policy-effectiveness")
def policy_effectiveness() -> dict:
    payload = _read_policy_effectiveness_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Policy effectiveness artifact missing; run scripts/run_policy_effectiveness.py first.",
        )
    return payload


@app.get("/api/allocation/market-phase")
def market_phase() -> dict:
    payload = _read_market_phase_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Market phase artifact missing; run scripts/run_market_phase_snapshot.py first.",
        )
    return payload


@app.get("/api/allocation/phase-effectiveness")
def phase_effectiveness() -> dict:
    payload = _read_phase_effectiveness_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Phase effectiveness artifact missing; run scripts/run_phase_effectiveness.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-simulation")
def exposure_simulation() -> dict:
    payload = _read_exposure_simulation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure simulation artifact missing; run scripts/run_exposure_simulation.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-effectiveness")
def exposure_effectiveness() -> dict:
    payload = _read_exposure_effectiveness_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure effectiveness artifact missing; run scripts/run_exposure_effectiveness.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-context-analysis")
def exposure_context_analysis() -> dict:
    payload = _read_exposure_context_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure context analysis artifact missing; run scripts/run_exposure_context_analysis.py first.",
        )
    return payload


@app.get("/api/allocation/balanced-context-audit")
def balanced_context_audit() -> dict:
    payload = _read_balanced_context_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Balanced context audit artifact missing; run scripts/run_balanced_context_audit.py first.",
        )
    return payload


@app.get("/api/allocation/balanced-candidate-failure-analysis")
def balanced_candidate_failure_analysis() -> dict:
    payload = _read_balanced_candidate_failure_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Balanced candidate failure analysis artifact missing; run scripts/run_balanced_candidate_failure_analysis.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-numeric-context")
def exposure_numeric_context() -> dict:
    payload = _read_exposure_numeric_context_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure numeric context artifact missing; run scripts/build_exposure_numeric_context.py first.",
        )
    return payload


@app.get("/api/allocation/macro-enhanced-context-analysis")
def macro_enhanced_context_analysis() -> dict:
    payload = _read_macro_enhanced_context_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Macro-enhanced context analysis artifact missing; run scripts/run_macro_enhanced_context_analysis.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-context-state-audit")
def exposure_context_state_audit() -> dict:
    payload = _read_exposure_context_state_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure context state audit artifact missing; run scripts/run_exposure_context_state_audit.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-gradient-analysis")
def exposure_gradient_analysis() -> dict:
    payload = _read_exposure_gradient_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure gradient analysis artifact missing; run scripts/run_exposure_gradient_analysis.py first.",
        )
    return payload


@app.get("/api/allocation/risk-gradient-robustness")
def risk_gradient_robustness() -> dict:
    payload = _read_risk_gradient_robustness_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk gradient robustness artifact missing; run scripts/run_risk_gradient_robustness.py first.",
        )
    return payload


@app.get("/api/allocation/risk-gradient-condition-analysis")
def risk_gradient_condition_analysis() -> dict:
    payload = _read_risk_gradient_condition_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk gradient condition analysis artifact missing; run scripts/run_risk_gradient_condition_analysis.py first.",
        )
    return payload


@app.get("/api/allocation/risk-gradient-candidate-rules")
def risk_gradient_candidate_rules() -> dict:
    payload = _read_risk_gradient_candidate_rules_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk gradient candidate rules artifact missing; run scripts/run_risk_gradient_candidate_rules.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-policy-validation")
def exposure_policy_validation() -> dict:
    payload = _read_exposure_policy_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure policy validation artifact missing; run scripts/run_exposure_policy_validation.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-decision-audit")
def exposure_decision_audit() -> dict:
    payload = _read_exposure_decision_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure decision audit artifact missing; run scripts/run_exposure_decision_audit.py first.",
        )
    return payload


@app.get("/api/allocation/exposure-context-score-audit")
def exposure_context_score_audit() -> dict:
    payload = _read_exposure_context_score_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Exposure context score audit artifact missing; run scripts/run_exposure_context_score_audit.py first.",
        )
    return payload


@app.get("/api/allocation/protection-score-validation")
def protection_score_validation() -> dict:
    payload = _read_protection_score_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Protection score validation artifact missing; run scripts/run_protection_score_validation.py first.",
        )
    return payload


@app.get("/api/allocation/two-axis-context-validation")
def two_axis_context_validation() -> dict:
    payload = _read_two_axis_context_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Two-axis context validation artifact missing; run scripts/run_two_axis_context_validation.py first.",
        )
    return payload


@app.get("/api/allocation/context-information-attribution")
def context_information_attribution() -> dict:
    payload = _read_context_information_attribution_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Context information attribution artifact missing; run scripts/run_context_information_attribution.py first.",
        )
    return payload


@app.get("/api/opportunity/research-foundation")
def opportunity_research_foundation() -> dict:
    payload = _read_opportunity_research_foundation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity research foundation artifact missing; run scripts/run_opportunity_research_foundation.py first.",
        )
    return payload


@app.get("/api/opportunity/context-features")
def opportunity_context_features() -> dict:
    payload = _read_opportunity_context_features_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity context features artifact missing; run scripts/run_opportunity_context_features.py first.",
        )
    return payload


@app.get("/api/opportunity/feature-validation")
def opportunity_feature_validation() -> dict:
    payload = _read_opportunity_feature_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity feature validation artifact missing; run scripts/run_opportunity_feature_validation.py first.",
        )
    return payload


@app.get("/api/opportunity/feature-attribution")
def opportunity_feature_attribution() -> dict:
    payload = _read_opportunity_feature_attribution_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity feature attribution artifact missing; run scripts/run_opportunity_feature_attribution.py first.",
        )
    return payload


@app.get("/api/opportunity/v7-architecture")
def opportunity_v7_architecture() -> dict:
    payload = _read_opportunity_v7_architecture_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Opportunity V7 architecture document missing; add docs/opportunity_research_v7_architecture.md first.",
        )
    return payload


@app.get("/api/decision/research-context")
def research_decision_context() -> dict:
    payload = _read_research_decision_context_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research decision context artifact missing; run scripts/run_research_decision_context.py first.",
        )
    return payload


@app.get("/api/decision/scenario-audit")
def research_decision_scenario_audit() -> dict:
    payload = _read_research_decision_scenario_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research decision scenario audit artifact missing; run scripts/run_research_decision_scenario_audit.py first.",
        )
    return payload


@app.get("/api/decision/contradiction-attribution")
def research_decision_contradiction() -> dict:
    payload = _read_research_decision_contradiction_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research decision contradiction artifact missing; run scripts/run_research_decision_contradiction.py first.",
        )
    return payload


@app.get("/api/decision/v8-architecture")
def research_decision_v8_architecture() -> dict:
    payload = _read_research_decision_v8_architecture_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research decision V8 architecture document missing; add docs/research_decision_v8_architecture.md first.",
        )
    return payload


@app.get("/api/allocation-research/architecture")
def allocation_research_architecture() -> dict:
    payload = _read_allocation_research_architecture_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation research architecture artifact missing; run scripts/audit_allocation_research_architecture.py first.",
        )
    return payload


@app.get("/api/allocation-research/evidence-freeze")
def allocation_research_evidence_freeze() -> dict:
    payload = _read_allocation_research_evidence_freeze_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation research evidence freeze artifact missing; run scripts/audit_allocation_research_evidence.py first.",
        )
    return payload


@app.get("/api/allocation-research/execution-runs")
def allocation_research_execution_runs() -> dict:
    payload = _read_allocation_research_execution_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation research execution artifact missing; run scripts/run_allocation_research_execution.py first.",
        )
    return payload


@app.get("/api/allocation-research/result-review")
def allocation_research_result_review() -> dict:
    payload = _read_allocation_research_result_review_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation research result review artifact missing; run scripts/run_allocation_research_result_review.py first.",
        )
    return payload


@app.get("/api/allocation-research/final-boundary")
def allocation_research_final_boundary() -> dict:
    payload = _read_allocation_research_final_boundary_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation research final boundary artifact missing; run scripts/run_allocation_research_final_boundary.py first.",
        )
    return payload


@app.get("/api/external-validation/protocol")
def external_validation_protocol() -> dict:
    payload = _read_external_validation_protocol_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="External validation protocol artifact missing; run scripts/run_external_validation_protocol.py first.",
        )
    return payload


@app.get("/api/external-validation/execution-runs")
def h2_external_validation_execution() -> dict:
    payload = _read_h2_external_validation_execution_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="H2 external validation execution artifact missing; run scripts/run_h2_external_validation_execution.py first.",
        )
    return payload


@app.get("/api/external-validation/result-freeze")
def h2_external_validation_result_freeze() -> dict:
    payload = _read_h2_external_validation_result_freeze_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="H2 external validation result freeze artifact missing; run scripts/run_h2_external_validation_result_freeze.py first.",
        )
    return payload


@app.get("/api/research-phase/closure")
def research_phase_closure() -> dict:
    payload = _read_research_phase_closure_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research phase closure artifact missing; run scripts/run_research_phase_closure.py first.",
        )
    return payload


@app.get("/api/implementation-boundary/research-to-implementation")
def research_to_implementation_boundary() -> dict:
    payload = _read_research_to_implementation_boundary_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research-to-implementation boundary artifact missing; run scripts/run_research_to_implementation_boundary.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/evidence-specification")
def implementation_readiness_evidence_specification() -> dict:
    payload = _read_implementation_readiness_evidence_specification_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Implementation readiness evidence specification artifact missing; run scripts/run_implementation_readiness_evidence_specification.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/evidence-audit")
def implementation_readiness_evidence_audit() -> dict:
    payload = _read_implementation_readiness_evidence_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Implementation readiness evidence audit artifact missing; run scripts/run_implementation_readiness_evidence_audit.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/evidence-submission-protocol")
def research_component_evidence_submission_protocol() -> dict:
    payload = _read_research_component_evidence_submission_protocol_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research component evidence submission protocol artifact missing; run scripts/run_research_component_evidence_submission_protocol.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/evidence-package-validator")
def evidence_package_validation_engine() -> dict:
    payload = _read_evidence_package_validation_engine_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Evidence package validation engine artifact missing; run scripts/run_evidence_package_validation_engine.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/invalid-evidence-example")
def invalid_evidence_package_rejection_example() -> dict:
    payload = _read_invalid_evidence_package_rejection_example_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Invalid evidence package rejection example artifact missing; run scripts/run_invalid_evidence_package_rejection_example.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/governance-freeze")
def implementation_readiness_governance_freeze() -> dict:
    payload = _read_implementation_readiness_governance_freeze_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Implementation readiness governance freeze artifact missing; run scripts/run_implementation_readiness_governance_freeze.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-evidence-package")
def risk_diagnostic_evidence_package() -> dict:
    payload = _read_risk_diagnostic_evidence_package_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic evidence package artifact missing; run scripts/run_risk_diagnostic_evidence_package.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-framework")
def risk_diagnostic_shadow_framework() -> dict:
    payload = _read_risk_diagnostic_shadow_framework_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow framework artifact missing; run scripts/run_risk_diagnostic_shadow_framework.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-log")
def risk_diagnostic_shadow_observation_log() -> dict:
    payload = _read_risk_diagnostic_shadow_observation_log_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow observation log artifact missing; run scripts/run_risk_diagnostic_shadow_observation_log.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-review")
def risk_diagnostic_shadow_observation_review() -> dict:
    payload = _read_risk_diagnostic_shadow_observation_review_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow observation review artifact missing; run scripts/run_risk_diagnostic_shadow_observation_review.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-manual-capture")
def risk_diagnostic_shadow_manual_event_capture() -> dict:
    payload = _read_risk_diagnostic_shadow_manual_event_capture_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow manual event capture artifact missing; run scripts/run_risk_diagnostic_shadow_manual_event_capture.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-quality-audit")
def risk_diagnostic_shadow_event_quality_audit() -> dict:
    payload = _read_risk_diagnostic_shadow_event_quality_audit_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow event quality audit artifact missing; run scripts/run_risk_diagnostic_shadow_event_quality_audit.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-first-event-workflow")
def risk_diagnostic_shadow_first_event_workflow() -> dict:
    payload = _read_risk_diagnostic_shadow_first_event_workflow_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow first event workflow artifact missing; run scripts/run_risk_diagnostic_shadow_first_event_workflow.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-event-input-package")
def risk_diagnostic_shadow_event_input_package() -> dict:
    payload = _read_risk_diagnostic_shadow_event_input_package_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow event input package artifact missing; run scripts/run_risk_diagnostic_shadow_event_input_package.py first.",
        )
    return payload


@app.get("/api/implementation-readiness/risk-diagnostic-shadow-evidence-dashboard")
def risk_diagnostic_shadow_evidence_dashboard() -> dict:
    payload = _read_risk_diagnostic_shadow_evidence_dashboard_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Risk diagnostic shadow evidence dashboard artifact missing; run scripts/run_risk_diagnostic_shadow_evidence_dashboard.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-direction")
def v15_strategy_direction_rebase() -> dict:
    payload = _read_v15_strategy_direction_rebase_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 strategy direction rebase artifact missing; run scripts/run_v15_strategy_direction_rebase.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-backtest-dataset")
def v15_backtest_dataset_manifest() -> dict:
    payload = _read_v15_backtest_dataset_manifest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 backtest dataset manifest artifact missing; run scripts/run_v15_backtest_dataset_builder.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-dataset-materialization")
def v15_backtest_dataset_materialization() -> dict:
    payload = _read_v15_backtest_dataset_materialization_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 backtest dataset materialization artifact missing; run scripts/run_v15_backtest_dataset_materializer.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-macro-drawdown-backtest")
def v15_macro_drawdown_backtest() -> dict:
    payload = _read_v15_macro_drawdown_backtest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 macro drawdown backtest artifact missing; run scripts/run_v15_macro_drawdown_backtest.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-macro-drawdown-robustness")
def v15_macro_drawdown_robustness() -> dict:
    payload = _read_v15_macro_drawdown_robustness_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 macro drawdown robustness artifact missing; run scripts/run_v15_macro_drawdown_robustness.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-point-in-time-phase-rebuild")
def v15_point_in_time_phase_rebuild() -> dict:
    payload = _read_v15_point_in_time_phase_rebuild_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 point-in-time phase rebuild artifact missing; run scripts/run_v15_point_in_time_phase_rebuild.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-late-cycle-overlay-manifest")
def v15_late_cycle_overlay_manifest() -> dict:
    payload = _read_v15_late_cycle_overlay_manifest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 late-cycle overlay manifest missing; run scripts/run_v15_point_in_time_phase_rebuild.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-point-in-time-snapshot-ledger")
def v15_point_in_time_snapshot_ledger() -> dict:
    payload = _read_v15_point_in_time_snapshot_ledger_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 point-in-time snapshot ledger missing; run scripts/run_v15_point_in_time_snapshot_ledger.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-point-in-time-snapshot-ledger-status")
def v15_point_in_time_snapshot_ledger_status() -> dict:
    payload = _read_v15_point_in_time_snapshot_ledger_status_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 point-in-time snapshot ledger status missing; run scripts/run_v15_point_in_time_snapshot_ledger.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-daily-snapshot-capture")
def v15_daily_snapshot_capture() -> dict:
    payload = _read_v15_daily_snapshot_capture_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 daily snapshot capture missing; run scripts/run_v15_daily_snapshot_capture.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-forward-paper-decision")
def v15_forward_paper_decision() -> dict:
    payload = _read_v15_forward_paper_decision_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 forward paper decision missing; run scripts/run_v15_daily_snapshot_capture.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-forward-observation-journal")
def v15_forward_observation_journal() -> dict:
    payload = _read_v15_forward_observation_journal_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 forward observation journal missing; run scripts/run_v15_daily_forward_update.py first.",
        )
    return payload


@app.get("/api/strategy-rebase/v15-forward-outcomes")
def v15_forward_outcomes() -> dict:
    payload = _read_v15_forward_outcomes_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="V15 forward outcomes missing; run scripts/run_v15_forward_outcome_intake.py first.",
        )
    return payload


@app.get("/api/allocation-research/hypotheses")
def allocation_research_hypotheses() -> dict:
    payload = _read_allocation_research_hypotheses_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation research hypotheses artifact missing; run scripts/run_allocation_hypothesis_audit.py first.",
        )
    return payload


@app.get("/api/allocation-research/validation-plan")
def allocation_validation_plan() -> dict:
    payload = _read_allocation_validation_plan_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation validation plan artifact missing; run scripts/run_allocation_validation_plan.py first.",
        )
    return payload


@app.get("/api/allocation-research/experiment-templates")
def allocation_experiment_templates() -> dict:
    payload = _read_allocation_experiment_templates_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation experiment templates artifact missing; run scripts/run_allocation_experiment_template.py first.",
        )
    return payload


@app.get("/api/allocation-research/experiment-results")
def allocation_experiment_results() -> dict:
    payload = _read_allocation_experiment_results_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation experiment Phase 0 results artifact missing; run scripts/run_allocation_experiment.py first.",
        )
    return payload


@app.get("/api/allocation-research/experiment-phase1-validation")
def allocation_experiment_phase1_validation() -> dict:
    payload = _read_allocation_experiment_phase1_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Allocation experiment Phase 1 validation artifact missing; run scripts/run_allocation_experiment_phase1.py first.",
        )
    return payload


@app.get("/api/allocation-research/research-candidate-gate")
def research_candidate_gate() -> dict:
    payload = _read_research_candidate_promotion_gate_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research candidate gate artifact missing; run scripts/run_research_candidate_promotion_gate.py first.",
        )
    return payload


@app.get("/api/allocation-research/research-candidate-deep-validation")
def research_candidate_deep_validation() -> dict:
    payload = _read_research_candidate_deep_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Research candidate deep validation artifact missing; run scripts/run_research_candidate_deep_validation.py first.",
        )
    return payload


@app.get("/api/style/structural-bull-validation")
def structural_style_validation() -> dict:
    payload = _read_structural_style_validation_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Structural style validation artifact missing; run scripts/run_structural_style_validation.py first.",
        )
    return payload


@app.get("/api/style/structural-bull-failure-analysis")
def structural_style_failure_analysis() -> dict:
    payload = _read_structural_style_failure_analysis_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Structural style failure analysis artifact missing; run scripts/run_structural_style_failure_analysis.py first.",
        )
    return payload


@app.get("/api/style/historical-context")
def historical_style_context() -> dict:
    payload = _read_historical_style_context_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Historical style context artifact missing; run scripts/build_historical_style_context.py first.",
        )
    return payload


@app.get("/api/style/historical-context-coverage")
def historical_style_context_coverage() -> dict:
    payload = _read_historical_style_context_coverage_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Historical style context coverage artifact missing; run scripts/audit_style_context_coverage.py first.",
        )
    return payload


@app.get("/api/style/structural-bull-context-attribution")
def structural_style_context_attribution() -> dict:
    payload = _read_structural_style_context_attribution_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Structural style context attribution artifact missing; run scripts/run_structural_style_context_attribution.py first.",
        )
    return payload


@app.get("/api/strategy-backtests/{strategy_id}")
def strategy_suite_backtest(strategy_id: str) -> dict:
    payload = _read_strategy_suite_backtest_payload(strategy_id)
    if not payload:
        raise HTTPException(
            status_code=503,
            detail=f"{STRATEGY_BACKTEST_IDS.get(strategy_id, strategy_id)} artifact missing; run scripts/run_strategy_backtest_suite.py first.",
        )
    return payload


@app.get("/api/shadow/current")
def shadow_current() -> dict:
    payload = _read_shadow_backtest_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="shadow backtest artifact missing; run scripts/run_shadow_backtest.py first.",
        )
    return payload


@app.get("/api/shadow/regime-attribution")
def shadow_regime_attribution() -> dict:
    payload = _read_regime_attribution_payload()
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="regime attribution artifact missing; run scripts/run_regime_attribution.py first.",
        )
    return payload


@app.get("/api/system/snapshot")
def system_snapshot() -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        return _system_snapshot_payload(snapshot)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/results/summary")
def results_summary(
    compact: bool = Query(
        False,
        description="When true, omit long backtest curves/signals and keep only fields needed by overview pages.",
    ),
) -> dict:
    try:
        snapshot = _current_portfolio_snapshot()
        current = snapshot["current"]
        risk_signal = snapshot["risk_signal"]
        exposure_decision = snapshot["risk_decision"]
        policy = snapshot["risk_policy"]
        portfolio_policy = snapshot["portfolio_policy"]
        portfolio_allocation = snapshot["portfolio_allocation"]
        strategy_policy = snapshot["strategy_policy"]
        strategy_route = snapshot["strategy_route"]
        execution_policy = snapshot["execution_policy"]
        execution = snapshot["execution"]
        system_snapshot_payload = _system_snapshot_payload(snapshot)
        meta_edge = _meta_edge_payload(snapshot)
        style_rotation = _style_rotation_payload(snapshot)
        etf_rotation_signal = _etf_rotation_signal_payload(style_rotation)
        etf_rotation_backtest = _read_etf_rotation_backtest_payload()
        macro_style_etf_backtest = _read_macro_style_etf_backtest_payload()
        alpha_portfolio_risk_validation = _read_alpha_portfolio_risk_validation_payload()
        alpha_robustness_validation = _read_alpha_robustness_validation_payload()
        residual_alpha_analysis = _read_residual_alpha_analysis_payload()
        style_allocation_snapshot = _read_style_allocation_snapshot_payload()
        style_validation = _read_style_validation_payload()
        style_incremental_analysis = _read_style_incremental_analysis_payload()
        allocation_policy_snapshot = _read_allocation_policy_snapshot_payload()
        allocation_policy_validation = _read_allocation_policy_validation_payload()
        opportunity_risk_snapshot = _read_opportunity_risk_snapshot_payload()
        opportunity_risk_policy = _read_opportunity_risk_policy_payload()
        policy_effectiveness = _read_policy_effectiveness_payload()
        market_phase = _read_market_phase_payload()
        macro_context_history = _read_macro_context_history_payload()
        phase_effectiveness = _read_phase_effectiveness_payload()
        exposure_simulation = _read_exposure_simulation_payload()
        exposure_effectiveness = _read_exposure_effectiveness_payload()
        exposure_context_analysis = _read_exposure_context_analysis_payload()
        balanced_context_audit = _read_balanced_context_audit_payload()
        balanced_candidate_failure_analysis = _read_balanced_candidate_failure_analysis_payload()
        exposure_numeric_context = _read_exposure_numeric_context_payload()
        macro_enhanced_context_analysis = _read_macro_enhanced_context_analysis_payload()
        exposure_context_state_audit = _read_exposure_context_state_audit_payload()
        exposure_gradient_analysis = _read_exposure_gradient_analysis_payload()
        risk_gradient_robustness = _read_risk_gradient_robustness_payload()
        risk_gradient_condition_analysis = _read_risk_gradient_condition_analysis_payload()
        risk_gradient_candidate_rules = _read_risk_gradient_candidate_rules_payload()
        exposure_policy_validation = _read_exposure_policy_validation_payload()
        exposure_decision_audit = _read_exposure_decision_audit_payload()
        exposure_context_score_audit = _read_exposure_context_score_audit_payload()
        protection_score_validation = _read_protection_score_validation_payload()
        two_axis_context_validation = _read_two_axis_context_validation_payload()
        context_information_attribution = _read_context_information_attribution_payload()
        opportunity_research_foundation = _read_opportunity_research_foundation_payload()
        opportunity_context_features = _read_opportunity_context_features_payload()
        opportunity_feature_validation = _read_opportunity_feature_validation_payload()
        opportunity_feature_attribution = _read_opportunity_feature_attribution_payload()
        opportunity_v7_architecture = _read_opportunity_v7_architecture_payload()
        research_decision_context = _read_research_decision_context_payload()
        research_decision_scenario_audit = _read_research_decision_scenario_audit_payload()
        research_decision_contradiction = _read_research_decision_contradiction_payload()
        research_decision_v8_architecture = _read_research_decision_v8_architecture_payload()
        allocation_research_architecture = _read_allocation_research_architecture_payload()
        allocation_research_evidence_freeze = _read_allocation_research_evidence_freeze_payload()
        allocation_research_execution = _read_allocation_research_execution_payload()
        allocation_research_result_review = _read_allocation_research_result_review_payload()
        allocation_research_final_boundary = _read_allocation_research_final_boundary_payload()
        external_validation_protocol = _read_external_validation_protocol_payload()
        h2_external_validation_execution = _read_h2_external_validation_execution_payload()
        h2_external_validation_result_freeze = _read_h2_external_validation_result_freeze_payload()
        research_phase_closure = _read_research_phase_closure_payload()
        research_to_implementation_boundary = _read_research_to_implementation_boundary_payload()
        implementation_readiness_evidence_specification = _read_implementation_readiness_evidence_specification_payload()
        implementation_readiness_evidence_audit = _read_implementation_readiness_evidence_audit_payload()
        research_component_evidence_submission_protocol = _read_research_component_evidence_submission_protocol_payload()
        evidence_package_validation_engine = _read_evidence_package_validation_engine_payload()
        invalid_evidence_package_rejection_example = _read_invalid_evidence_package_rejection_example_payload()
        implementation_readiness_governance_freeze = _read_implementation_readiness_governance_freeze_payload()
        risk_diagnostic_evidence_package = _read_risk_diagnostic_evidence_package_payload()
        risk_diagnostic_shadow_framework = _read_risk_diagnostic_shadow_framework_payload()
        risk_diagnostic_shadow_observation_log = _read_risk_diagnostic_shadow_observation_log_payload()
        risk_diagnostic_shadow_observation_review = _read_risk_diagnostic_shadow_observation_review_payload()
        risk_diagnostic_shadow_manual_event_capture = _read_risk_diagnostic_shadow_manual_event_capture_payload()
        risk_diagnostic_shadow_event_quality_audit = _read_risk_diagnostic_shadow_event_quality_audit_payload()
        risk_diagnostic_shadow_first_event_workflow = _read_risk_diagnostic_shadow_first_event_workflow_payload()
        risk_diagnostic_shadow_event_input_package = _read_risk_diagnostic_shadow_event_input_package_payload()
        risk_diagnostic_shadow_evidence_dashboard = _read_risk_diagnostic_shadow_evidence_dashboard_payload()
        v15_strategy_direction_rebase = _read_v15_strategy_direction_rebase_payload()
        v15_backtest_dataset_manifest = _read_v15_backtest_dataset_manifest_payload()
        v15_backtest_dataset_materialization = _read_v15_backtest_dataset_materialization_payload()
        v15_macro_drawdown_backtest = _read_v15_macro_drawdown_backtest_payload()
        v15_macro_drawdown_robustness = _read_v15_macro_drawdown_robustness_payload()
        v15_point_in_time_phase_rebuild = _read_v15_point_in_time_phase_rebuild_payload()
        v15_late_cycle_overlay_manifest = _read_v15_late_cycle_overlay_manifest_payload()
        v15_point_in_time_snapshot_ledger_status = _read_v15_point_in_time_snapshot_ledger_status_payload()
        v15_daily_snapshot_capture = _read_v15_daily_snapshot_capture_payload()
        v15_forward_paper_decision = _read_v15_forward_paper_decision_payload()
        v15_forward_observation_journal = _read_v15_forward_observation_journal_payload()
        v15_forward_outcomes = _read_v15_forward_outcomes_payload()
        allocation_research_hypotheses = _read_allocation_research_hypotheses_payload()
        allocation_validation_plan = _read_allocation_validation_plan_payload()
        allocation_experiment_templates = _read_allocation_experiment_templates_payload()
        allocation_experiment_results = _read_allocation_experiment_results_payload()
        allocation_experiment_phase1_validation = _read_allocation_experiment_phase1_validation_payload()
        research_candidate_promotion_gate = _read_research_candidate_promotion_gate_payload()
        research_candidate_deep_validation = _read_research_candidate_deep_validation_payload()
        structural_style_validation = _read_structural_style_validation_payload()
        structural_style_failure_analysis = _read_structural_style_failure_analysis_payload()
        historical_style_context = _read_historical_style_context_payload()
        historical_style_context_coverage = _read_historical_style_context_coverage_payload()
        structural_style_context_attribution = _read_structural_style_context_attribution_payload()
        strategy_suite_backtests = _read_strategy_suite_summaries()
        if compact:
            etf_rotation_backtest = _compact_backtest_payload(etf_rotation_backtest)
            macro_style_etf_backtest = _compact_backtest_payload(macro_style_etf_backtest)
            allocation_policy_validation = _compact_policy_validation_payload(allocation_policy_validation)
            opportunity_risk_snapshot = _compact_opportunity_risk_payload(opportunity_risk_snapshot)
            opportunity_risk_policy = _compact_opportunity_risk_policy_payload(opportunity_risk_policy)
            policy_effectiveness = _compact_policy_effectiveness_payload(policy_effectiveness)
            market_phase = _compact_market_phase_payload(market_phase)
            macro_context_history = _compact_macro_context_history_payload(macro_context_history)
            phase_effectiveness = _compact_phase_effectiveness_payload(phase_effectiveness)
            exposure_simulation = _compact_exposure_simulation_payload(exposure_simulation)
            exposure_effectiveness = _compact_exposure_effectiveness_payload(exposure_effectiveness)
            exposure_context_analysis = _compact_exposure_context_analysis_payload(exposure_context_analysis)
            balanced_context_audit = _compact_balanced_context_audit_payload(balanced_context_audit)
            balanced_candidate_failure_analysis = _compact_balanced_candidate_failure_analysis_payload(balanced_candidate_failure_analysis)
            exposure_numeric_context = _compact_exposure_numeric_context_payload(exposure_numeric_context)
            macro_enhanced_context_analysis = _compact_macro_enhanced_context_analysis_payload(macro_enhanced_context_analysis)
            exposure_context_state_audit = _compact_exposure_context_state_audit_payload(exposure_context_state_audit)
            exposure_gradient_analysis = _compact_exposure_gradient_analysis_payload(exposure_gradient_analysis)
            risk_gradient_robustness = _compact_risk_gradient_robustness_payload(risk_gradient_robustness)
            risk_gradient_condition_analysis = _compact_risk_gradient_condition_analysis_payload(risk_gradient_condition_analysis)
            risk_gradient_candidate_rules = _compact_risk_gradient_candidate_rules_payload(risk_gradient_candidate_rules)
            exposure_policy_validation = _compact_exposure_policy_validation_payload(exposure_policy_validation)
            exposure_decision_audit = _compact_exposure_decision_audit_payload(exposure_decision_audit)
            exposure_context_score_audit = _compact_exposure_context_score_audit_payload(exposure_context_score_audit)
            protection_score_validation = _compact_protection_score_validation_payload(protection_score_validation)
            two_axis_context_validation = _compact_two_axis_context_validation_payload(two_axis_context_validation)
            context_information_attribution = _compact_context_information_attribution_payload(context_information_attribution)
            opportunity_research_foundation = _compact_opportunity_research_foundation_payload(opportunity_research_foundation)
            opportunity_context_features = _compact_opportunity_context_features_payload(opportunity_context_features)
            opportunity_feature_validation = _compact_opportunity_feature_validation_payload(opportunity_feature_validation)
            opportunity_feature_attribution = _compact_opportunity_feature_attribution_payload(opportunity_feature_attribution)
            opportunity_v7_architecture = _compact_opportunity_v7_architecture_payload(opportunity_v7_architecture)
            research_decision_context = _compact_research_decision_context_payload(research_decision_context)
            research_decision_scenario_audit = _compact_research_decision_scenario_audit_payload(research_decision_scenario_audit)
            research_decision_contradiction = _compact_research_decision_contradiction_payload(research_decision_contradiction)
            research_decision_v8_architecture = _compact_research_decision_v8_architecture_payload(research_decision_v8_architecture)
            allocation_research_architecture = _compact_allocation_research_architecture_payload(allocation_research_architecture)
            allocation_research_evidence_freeze = _compact_allocation_research_evidence_freeze_payload(allocation_research_evidence_freeze)
            allocation_research_execution = _compact_allocation_research_execution_payload(allocation_research_execution)
            allocation_research_result_review = _compact_allocation_research_result_review_payload(allocation_research_result_review)
            allocation_research_final_boundary = _compact_allocation_research_final_boundary_payload(allocation_research_final_boundary)
            external_validation_protocol = _compact_external_validation_protocol_payload(external_validation_protocol)
            h2_external_validation_execution = _compact_h2_external_validation_execution_payload(h2_external_validation_execution)
            h2_external_validation_result_freeze = _compact_h2_external_validation_result_freeze_payload(h2_external_validation_result_freeze)
            research_phase_closure = _compact_research_phase_closure_payload(research_phase_closure)
            research_to_implementation_boundary = _compact_research_to_implementation_boundary_payload(research_to_implementation_boundary)
            implementation_readiness_evidence_specification = _compact_implementation_readiness_evidence_specification_payload(implementation_readiness_evidence_specification)
            implementation_readiness_evidence_audit = _compact_implementation_readiness_evidence_audit_payload(implementation_readiness_evidence_audit)
            research_component_evidence_submission_protocol = _compact_research_component_evidence_submission_protocol_payload(research_component_evidence_submission_protocol)
            evidence_package_validation_engine = _compact_evidence_package_validation_engine_payload(evidence_package_validation_engine)
            invalid_evidence_package_rejection_example = _compact_invalid_evidence_package_rejection_example_payload(invalid_evidence_package_rejection_example)
            implementation_readiness_governance_freeze = _compact_implementation_readiness_governance_freeze_payload(implementation_readiness_governance_freeze)
            risk_diagnostic_evidence_package = _compact_risk_diagnostic_evidence_package_payload(risk_diagnostic_evidence_package)
            risk_diagnostic_shadow_framework = _compact_risk_diagnostic_shadow_framework_payload(risk_diagnostic_shadow_framework)
            risk_diagnostic_shadow_observation_log = _compact_risk_diagnostic_shadow_observation_log_payload(risk_diagnostic_shadow_observation_log)
            risk_diagnostic_shadow_observation_review = _compact_risk_diagnostic_shadow_observation_review_payload(risk_diagnostic_shadow_observation_review)
            risk_diagnostic_shadow_manual_event_capture = _compact_risk_diagnostic_shadow_manual_event_capture_payload(risk_diagnostic_shadow_manual_event_capture)
            risk_diagnostic_shadow_event_quality_audit = _compact_risk_diagnostic_shadow_event_quality_audit_payload(risk_diagnostic_shadow_event_quality_audit)
            risk_diagnostic_shadow_first_event_workflow = _compact_risk_diagnostic_shadow_first_event_workflow_payload(risk_diagnostic_shadow_first_event_workflow)
            risk_diagnostic_shadow_event_input_package = _compact_risk_diagnostic_shadow_event_input_package_payload(risk_diagnostic_shadow_event_input_package)
            risk_diagnostic_shadow_evidence_dashboard = _compact_risk_diagnostic_shadow_evidence_dashboard_payload(risk_diagnostic_shadow_evidence_dashboard)
            v15_strategy_direction_rebase = _compact_v15_strategy_direction_rebase_payload(v15_strategy_direction_rebase)
            v15_backtest_dataset_manifest = _compact_v15_backtest_dataset_manifest_payload(v15_backtest_dataset_manifest)
            v15_backtest_dataset_materialization = _compact_v15_backtest_dataset_materialization_payload(v15_backtest_dataset_materialization)
            v15_macro_drawdown_backtest = _compact_v15_macro_drawdown_backtest_payload(v15_macro_drawdown_backtest)
            v15_macro_drawdown_robustness = _compact_v15_macro_drawdown_robustness_payload(v15_macro_drawdown_robustness)
            v15_point_in_time_phase_rebuild = _compact_v15_point_in_time_phase_rebuild_payload(v15_point_in_time_phase_rebuild)
            v15_late_cycle_overlay_manifest = _compact_v15_late_cycle_overlay_manifest_payload(v15_late_cycle_overlay_manifest)
            v15_point_in_time_snapshot_ledger_status = _compact_v15_point_in_time_snapshot_ledger_status_payload(v15_point_in_time_snapshot_ledger_status)
            v15_daily_snapshot_capture = _compact_v15_daily_snapshot_capture_payload(v15_daily_snapshot_capture)
            v15_forward_paper_decision = _compact_v15_forward_paper_decision_payload(v15_forward_paper_decision)
            v15_forward_observation_journal = _compact_v15_forward_observation_journal_payload(v15_forward_observation_journal)
            v15_forward_outcomes = _compact_v15_forward_outcomes_payload(v15_forward_outcomes)
            allocation_research_hypotheses = _compact_allocation_research_hypotheses_payload(allocation_research_hypotheses)
            allocation_validation_plan = _compact_allocation_validation_plan_payload(allocation_validation_plan)
            allocation_experiment_templates = _compact_allocation_experiment_templates_payload(allocation_experiment_templates)
            allocation_experiment_results = _compact_allocation_experiment_results_payload(allocation_experiment_results)
            allocation_experiment_phase1_validation = _compact_allocation_experiment_phase1_validation_payload(allocation_experiment_phase1_validation)
            research_candidate_promotion_gate = _compact_research_candidate_promotion_gate_payload(research_candidate_promotion_gate)
            research_candidate_deep_validation = _compact_research_candidate_deep_validation_payload(research_candidate_deep_validation)
        shadow_backtest = _read_shadow_backtest_payload()
        regime_attribution = _read_regime_attribution_payload()

        hazard_rows = _read_data_json("hazard_dataset.json") or []
        structural_hazard_rows = _read_data_json("structural_hazard_dataset.json") or []
        survival_rows = _read_data_json("survival_dataset.json") or []
        structural_survival_rows = _read_data_json("structural_survival_dataset.json") or []
        model_evaluation = _read_data_json("hazard_model_evaluation.json")
        model_sensitivity = _read_data_json("hazard_model_sensitivity.json")

        hazard_raw = _event_summary(hazard_rows)
        hazard_structural = _event_summary(structural_hazard_rows)
        survival_raw = _event_summary(survival_rows, event_key="event")
        survival_structural = _event_summary(structural_survival_rows, event_key="event")

        return {
            "as_of": current["as_of"],
            "risk": {
                "signal": risk_signal,
                "decision": exposure_decision,
                "policy": _policy_summary(policy),
            },
            "portfolio": {
                "allocation": portfolio_allocation,
                "policy": _portfolio_policy_summary(portfolio_policy),
            },
            "strategy_route": {
                "route": strategy_route,
                "policy": _strategy_policy_summary(strategy_policy),
            },
            "execution": {
                "simulation": execution,
                "policy": _execution_policy_summary(execution_policy),
            },
            "meta_edge": meta_edge,
            "style_rotation": style_rotation,
            "etf_rotation_signal": etf_rotation_signal,
            "etf_rotation_backtest": etf_rotation_backtest,
            "macro_style_etf_backtest": macro_style_etf_backtest,
            "alpha_portfolio_risk_validation": alpha_portfolio_risk_validation,
            "alpha_robustness_validation": alpha_robustness_validation,
            "residual_alpha_analysis": residual_alpha_analysis,
            "style_allocation_snapshot": style_allocation_snapshot,
            "style_validation": style_validation,
            "style_incremental_analysis": style_incremental_analysis,
            "allocation_policy_snapshot": allocation_policy_snapshot,
            "allocation_policy_validation": allocation_policy_validation,
            "opportunity_risk_snapshot": opportunity_risk_snapshot,
            "opportunity_risk_policy": opportunity_risk_policy,
            "policy_effectiveness": policy_effectiveness,
            "market_phase": market_phase,
            "macro_context_history": macro_context_history,
            "phase_effectiveness": phase_effectiveness,
            "exposure_simulation": exposure_simulation,
            "exposure_effectiveness": exposure_effectiveness,
            "exposure_context_analysis": exposure_context_analysis,
            "balanced_context_audit": balanced_context_audit,
            "balanced_candidate_failure_analysis": balanced_candidate_failure_analysis,
            "exposure_numeric_context": exposure_numeric_context,
            "macro_enhanced_context_analysis": macro_enhanced_context_analysis,
            "exposure_context_state_audit": exposure_context_state_audit,
            "exposure_gradient_analysis": exposure_gradient_analysis,
            "risk_gradient_robustness": risk_gradient_robustness,
            "risk_gradient_condition_analysis": risk_gradient_condition_analysis,
            "risk_gradient_candidate_rules": risk_gradient_candidate_rules,
            "exposure_policy_validation": exposure_policy_validation,
            "exposure_decision_audit": exposure_decision_audit,
            "exposure_context_score_audit": exposure_context_score_audit,
            "protection_score_validation": protection_score_validation,
            "two_axis_context_validation": two_axis_context_validation,
            "context_information_attribution": context_information_attribution,
            "opportunity_research_foundation": opportunity_research_foundation,
            "opportunity_context_features": opportunity_context_features,
            "opportunity_feature_validation": opportunity_feature_validation,
            "opportunity_feature_attribution": opportunity_feature_attribution,
            "opportunity_v7_architecture": opportunity_v7_architecture,
            "research_decision_context": research_decision_context,
            "research_decision_scenario_audit": research_decision_scenario_audit,
            "research_decision_contradiction": research_decision_contradiction,
            "research_decision_v8_architecture": research_decision_v8_architecture,
            "allocation_research_architecture": allocation_research_architecture,
            "allocation_research_evidence_freeze": allocation_research_evidence_freeze,
            "allocation_research_execution": allocation_research_execution,
            "allocation_research_result_review": allocation_research_result_review,
            "allocation_research_final_boundary": allocation_research_final_boundary,
            "external_validation_protocol": external_validation_protocol,
            "h2_external_validation_execution": h2_external_validation_execution,
            "h2_external_validation_result_freeze": h2_external_validation_result_freeze,
            "research_phase_closure": research_phase_closure,
            "research_to_implementation_boundary": research_to_implementation_boundary,
            "implementation_readiness_evidence_specification": implementation_readiness_evidence_specification,
            "implementation_readiness_evidence_audit": implementation_readiness_evidence_audit,
            "research_component_evidence_submission_protocol": research_component_evidence_submission_protocol,
            "evidence_package_validation_engine": evidence_package_validation_engine,
            "invalid_evidence_package_rejection_example": invalid_evidence_package_rejection_example,
            "implementation_readiness_governance_freeze": implementation_readiness_governance_freeze,
            "risk_diagnostic_evidence_package": risk_diagnostic_evidence_package,
            "risk_diagnostic_shadow_framework": risk_diagnostic_shadow_framework,
            "risk_diagnostic_shadow_observation_log": risk_diagnostic_shadow_observation_log,
            "risk_diagnostic_shadow_observation_review": risk_diagnostic_shadow_observation_review,
            "risk_diagnostic_shadow_manual_event_capture": risk_diagnostic_shadow_manual_event_capture,
            "risk_diagnostic_shadow_event_quality_audit": risk_diagnostic_shadow_event_quality_audit,
            "risk_diagnostic_shadow_first_event_workflow": risk_diagnostic_shadow_first_event_workflow,
            "risk_diagnostic_shadow_event_input_package": risk_diagnostic_shadow_event_input_package,
            "risk_diagnostic_shadow_evidence_dashboard": risk_diagnostic_shadow_evidence_dashboard,
            "v15_strategy_direction_rebase": v15_strategy_direction_rebase,
            "v15_backtest_dataset_manifest": v15_backtest_dataset_manifest,
            "v15_backtest_dataset_materialization": v15_backtest_dataset_materialization,
            "v15_macro_drawdown_backtest": v15_macro_drawdown_backtest,
            "v15_macro_drawdown_robustness": v15_macro_drawdown_robustness,
            "v15_point_in_time_phase_rebuild": v15_point_in_time_phase_rebuild,
            "v15_late_cycle_overlay_manifest": v15_late_cycle_overlay_manifest,
            "v15_point_in_time_snapshot_ledger_status": v15_point_in_time_snapshot_ledger_status,
            "v15_daily_snapshot_capture": v15_daily_snapshot_capture,
            "v15_forward_paper_decision": v15_forward_paper_decision,
            "v15_forward_observation_journal": v15_forward_observation_journal,
            "v15_forward_outcomes": v15_forward_outcomes,
            "allocation_research_hypotheses": allocation_research_hypotheses,
            "allocation_validation_plan": allocation_validation_plan,
            "allocation_experiment_templates": allocation_experiment_templates,
            "allocation_experiment_results": allocation_experiment_results,
            "allocation_experiment_phase1_validation": allocation_experiment_phase1_validation,
            "research_candidate_promotion_gate": research_candidate_promotion_gate,
            "research_candidate_deep_validation": research_candidate_deep_validation,
            "structural_style_validation": structural_style_validation,
            "structural_style_failure_analysis": structural_style_failure_analysis,
            "historical_style_context": historical_style_context,
            "historical_style_context_coverage": historical_style_context_coverage,
            "structural_style_context_attribution": structural_style_context_attribution,
            "strategy_suite_backtests": strategy_suite_backtests,
            "shadow_backtest": shadow_backtest,
            "regime_attribution": regime_attribution,
            "system": system_snapshot_payload,
            "hazard": {
                "raw": {
                    **hazard_raw,
                    "regime_counts": _regime_counts(hazard_rows, "regime"),
                },
                "structural": {
                    **hazard_structural,
                    "regime_counts": _regime_counts(structural_hazard_rows, "structural_regime"),
                    "label_types": dict(Counter(str(row.get("label_type", "unknown")) for row in structural_hazard_rows)),
                },
            },
            "survival": {
                "raw": {
                    **survival_raw,
                    "durations": _duration_summary(survival_rows, "regime"),
                },
                "structural": {
                    **survival_structural,
                    "durations": _duration_summary(structural_survival_rows, "structural_regime"),
                },
            },
            "model_validation": {
                "default": _model_validation_summary(model_evaluation),
                "sensitivity": (model_sensitivity or {}).get("summary", {}),
            },
            "conclusions": [
                "FINAL 已冻结系统边界：5 层决策链稳定，策略已锁定，执行层保持 simulation-only。",
                "R3.1 已把策略路由转成执行意图和模拟指令，但不连接券商、不生成真实订单。",
                "M1.1 已新增 Meta Signal Engine，只检测系统内部矛盾信号，不预测收益、不选股、不改变既有风控链路。",
                "A1.1 已新增风格评分与 ETF universe 层，把 regime、风险评分、宽度、流动性和波动稳定度映射到 ETF 候选池。",
                "A1.2 已新增 ETF 轮动信号层，把风格评分、ETF 相对强弱和排名稳定性转成 simulation-only 目标权重建议。",
                "A1.3 已新增 ETF 轮动回测与 Alpha 验证层，用历史回放检验轮动信号是否跑赢 510500、510300 和等权 ETF basket。",
                "M2.1 已新增 Macro-Style-ETF 分层组合回测，把宏观周期、风格分配和 ETF 执行三层解耦，并与 A1、510300、510500 和等权 ETF basket 对比。",
                "新增三套独立 ETF 策略回测：红利低波防守、行业 ETF 动量空仓、股债金现金四资产轮动；页面按策略独立展示图表、指标和再平衡记录。",
                "V4.2 已重放固定 V4.1 风险预算规则并输出历史矛盾审计，硬矛盾和软复核项只用于规则评估，不自动改规则、不生成交易。",
                "V4.3 已把机会状态与风险状态拆成两个轴，识别结构机会和拥挤高位风险是否同时存在；该层仍不输出仓位、ETF 或交易。",
                "V4.4 已把机会状态 + 风险状态映射为定性政策模式，并用历史状态重放验证政策模式分布；该层仍不输出仓位、ETF、权重或交易。",
                "V4.5 已固定 V4.4 规则做反事实解释力审计，比较 structural_state、机会风险二维状态和 policy_mode 对未来环境标签的区分力；该层不调阈值、不生成仓位或交易。",
                "V4.6 已新增市场阶段第三维，把同样的机会/风险拆成 Early、Expansion、Rotation、Late、Contraction 等阶段解释；该层仍不输出仓位、ETF、权重或交易。",
                "V4.7 已固定 V4.6 阶段规则做解释力和转移审计，标出 phase 未优于 structural_state、EXPANSION 样本太少和熊市阶段漏判等复核项；该层不调阈值、不生成仓位或交易。",
                "V5.1 已把固定政策模式映射为 DEFENSIVE/LOW/BALANCED/HIGH/OFFENSIVE 定性暴露等级，并审计历史矛盾和机会错失；该层只做模拟验证，不输出仓位百分比、ETF、权重或交易信号。",
                "V5.2 已固定 V5.1 暴露等级做有效性审计，发现 BALANCED 过宽、HIGH/OFFENSIVE 缺失且等级有序性未被证明；该层只做审计，不改规则、不输出交易。",
                "V5.3 已只分析 BALANCED 桶，拆解失败、机会错失和中性样本的上下文来源，结论是先拆 BALANCED 再考虑 mapper 调整；该层不改规则、不加等级、不输出交易。",
                "V5.4 已对 BALANCED_RISK、BALANCED_OPPORTUNITY、BALANCED_NEUTRAL 研究候选标签做质量审计，结论是候选仍未准备好进入正式 mapper；该层不改规则、不新增正式等级。",
                "V5.5 已固定 V5.4 候选标签做失败与机会错失归因，发现风险候选可能包含修复期误判，机会候选可能是结构轮动被控制层压制；仍需数值上下文增强后才能改规则。",
                "V5.8 已把 V5.6 数值上下文和 V5.7 宏观历史上下文接入 BALANCED 候选重新归因，宏观与市场数值能提高诊断清晰度，但仍不改 mapper、不新增正式状态、不输出仓位或交易。",
                "V5.9 已设计 Recovery、Structural Opportunity、Risk、Neutral 四类 BALANCED 研究候选状态并审计分离度，结果显示可解释但风险/机会边际仍弱，不能进入正式 mapper。",
                "V5.10 已从离散状态转向连续风险/机会梯度，风险梯度高分桶能明显抬升未来失败率，但机会梯度暂未显示区分力；该层仍不改 mapper、不输出仓位或交易。",
                "V5.11 已固定 V5.10 风险梯度做分阶段稳健性审计，结论是总体边际可见但跨阶段稳定性证据不足，仍不能进入 mapper 或仓位规则。",
                "V5.12 已按机会状态、市场阶段、风险状态和组合条件拆解风险梯度适用环境，发现拥挤和早周期条件下更有效，但样本不足较多，仍只做条件解释。",
                "V5.13 已把 V5.12 正向条件压缩为 5 个最小候选并审计稳定性，只有 2 个进入主研究候选，0 个可规则化。",
                "V6.1 已固定 V5.1 暴露模拟叠加 V5 风险诊断做历史验证，风险提示捕获率低且误警率高，暂不能改善 policy。",
                "V6.2 已设计 research-only decision context 标签并审计，风险/机会分离均弱，仍不能进入暴露决策。",
                "V6.3 已生成 participation/protection 连续上下文分数并审计，protection 对风险有可见分离，但 participation 对机会仍弱，暂不改策略。",
                "S1.1 已新增仓位风控回测，用历史 R2 动态仓位回放 510500 基准收益，输出权益曲线、Alpha 和回撤。",
                "S1.2 已按牛熊状态拆解风控仓位策略收益来源，识别牛市参与不足是主要拖累，熊市防守是主要正贡献。",
                "R2.2 已把组合配置转译为策略可执行约束，页面展示可启用策略、禁用原因和策略预算。",
                "R2.1 已把风险引擎输出落到组合层，页面展示总仓位、现金比例和策略资金分配。",
                "结构化事件标签把原始频繁跳变压缩为更接近主周期切换的样本，适合做风险观察而不是短线交易信号。",
                "默认结构化模型相对随机基准有正向识别力，但敏感性测试不稳定，不能直接解释为确定性预测。",
                "波动单因子在默认切分中强于多因子逻辑模型，说明当前阶段的风险提示主要来自波动与市场宽度压力。",
                "最终落地结果是按牛熊状态调节仓位与交易模式的风控层，而不是自动买卖或收益承诺。",
            ],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/regime/history")
def regime_history(
    start: str = Query(..., description="YYYYMMDD"),
    end: str = Query(..., description="YYYYMMDD"),
) -> dict:
    try:
        start_date = normalize_trade_date(start)
        end_date = normalize_trade_date(end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start must be earlier than or equal to end")

    warmup_start = _calendar_shift(start_date, -540)
    index_df = _load_index_window(warmup_start, end_date)
    target_dates = index_df[
        (index_df["trade_date"] >= start_date) & (index_df["trade_date"] <= end_date)
    ]["trade_date"].astype(str).tolist()

    if len(target_dates) > 80:
        raise HTTPException(status_code=422, detail="history range is limited to 80 trading days")

    series = []
    for trade_date in target_dates:
        index_slice = index_df[index_df["trade_date"] <= trade_date]
        market_daily = get_market_daily(trade_date)
        market_history = get_market_history_sample(
            market_daily,
            _calendar_shift(trade_date, -370),
            trade_date,
            sample_size=BREADTH_HISTORY_SAMPLE_SIZE,
        )
        hsgt = _load_hsgt_for_index(index_df, trade_date)
        result = analyze_index_regime(
            index_slice,
            market_daily_df=market_daily,
            market_history_df=market_history,
            hsgt_df=hsgt,
        )
        feature_row = build_feature_frame(index_slice).iloc[-1]
        series.append(
            {
                "as_of": result["as_of"],
                "regime": result["regime"],
                "confidence": result["confidence"],
                "regime_score": result["regime_score"],
                "sub_scores": result["sub_scores"],
                "index": {
                    "close": round(float(feature_row["close"]), 4),
                    "ma120": None if pd.isna(feature_row["ma120"]) else round(float(feature_row["ma120"]), 4),
                },
            }
        )

    return {"start": start_date, "end": end_date, "items": series}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web.app:app", host="127.0.0.1", port=WEB_PORT, reload=False)
