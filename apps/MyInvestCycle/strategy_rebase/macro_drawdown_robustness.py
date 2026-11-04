from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from strategy_rebase.macro_drawdown_backtest import (
    CASH_ANNUAL_RETURN,
    TRANSACTION_COST_BPS,
    TRADING_DAYS,
    _build_curves,
    _metrics,
)


DEFAULT_INPUT_PATH = DATA_DIR / "v15_macro_drawdown_backtest_result.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_macro_drawdown_robustness_result.json"
THRESHOLD_SCALES = (0.75, 1.0, 1.25)
EXPOSURE_SCALES = (0.75, 1.0, 1.25)
COST_BPS_LEVELS = (0, 5, 10, TRANSACTION_COST_BPS)

BASE_RULES: dict[str, tuple[float, float, float]] = {
    "EARLY_CYCLE": (0.85, 1.00, 0.08),
    "EXPANSION": (0.85, 1.00, 0.08),
    "ROTATION": (0.65, 0.75, 0.10),
    "LATE_CYCLE": (0.55, 0.30, 0.05),
    "CONTRACTION": (0.25, 0.15, 0.05),
    "UNKNOWN": (0.50, 0.50, 1.00),
}


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _scaled_exposure(value: float, scale: float) -> float:
    return min(1.0, max(0.0, 0.5 + (value - 0.5) * scale))


def _variant_id(threshold_scale: float, exposure_scale: float) -> str:
    return f"t{round(threshold_scale * 100):03d}_e{round(exposure_scale * 100):03d}"


def _target_exposure(phase: str, drawdown: float, threshold_scale: float, exposure_scale: float) -> float:
    base, triggered, threshold = BASE_RULES.get(phase, BASE_RULES["UNKNOWN"])
    selected = triggered if drawdown <= -(threshold * threshold_scale) else base
    return _scaled_exposure(selected, exposure_scale)


def _simulate(
    rows: list[dict[str, object]],
    csi_equity: list[float],
    *,
    threshold_scale: float,
    exposure_scale: float,
    cost_bps: int = 0,
) -> dict[str, object]:
    if len(rows) != len(csi_equity):
        raise ValueError("rows and csi_equity must have the same length")
    dates = [str(row["date"]) for row in rows]
    cash_daily = CASH_ANNUAL_RETURN / TRADING_DAYS
    cost_rate = cost_bps / 10_000
    target = [
        _target_exposure(
            str(row.get("phase") or "UNKNOWN"),
            float(row.get("drawdown") or 0.0),
            threshold_scale,
            exposure_scale,
        )
        for row in rows
    ]
    equity = [1.0]
    applied = [target[0] if target else 0.5]
    daily_turnover = [0.0]
    for index in range(1, len(rows)):
        exposure = target[index - 1]
        previous_exposure = applied[-1]
        turnover = abs(exposure - previous_exposure)
        csi_return = csi_equity[index] / csi_equity[index - 1] - 1.0
        strategy_return = exposure * csi_return + (1.0 - exposure) * cash_daily - turnover * cost_rate
        equity.append(equity[-1] * (1.0 + strategy_return))
        applied.append(exposure)
        daily_turnover.append(turnover)
    metrics = _metrics(dates, equity, benchmark_cagr=_metrics(dates, csi_equity).get("CAGR"))
    metrics.update(
        {
            "variant_id": _variant_id(threshold_scale, exposure_scale),
            "threshold_scale": threshold_scale,
            "exposure_scale": exposure_scale,
            "cost_bps": cost_bps,
            "average_exposure": round(sum(applied) / len(applied), 6) if applied else None,
            "one_way_turnover": round(sum(daily_turnover), 6),
            "annualized_turnover": round(sum(daily_turnover) / max(len(rows) / TRADING_DAYS, 1 / TRADING_DAYS), 6),
        }
    )
    return {
        "dates": dates,
        "equity": equity,
        "applied_exposure": applied,
        "daily_turnover": daily_turnover,
        "metrics": metrics,
    }


def _slice_inputs(
    rows: list[dict[str, object]],
    csi_equity: list[float],
    *,
    start: str | None = None,
    end: str | None = None,
) -> tuple[list[dict[str, object]], list[float]]:
    selected = [
        (row, value)
        for row, value in zip(rows, csi_equity, strict=False)
        if (start is None or str(row["date"]) >= start) and (end is None or str(row["date"]) <= end)
    ]
    if not selected:
        return [], []
    base = selected[0][1]
    return [row for row, _ in selected], [value / base for _, value in selected]


def _rank_key(metrics: Mapping[str, object]) -> tuple[float, float, float]:
    calmar = float(metrics.get("calmar") or -999.0)
    cagr = float(metrics.get("CAGR") or -999.0)
    max_drawdown = float(metrics.get("max_drawdown") or -1.0)
    return calmar, cagr, max_drawdown


def _walk_forward(
    rows: list[dict[str, object]],
    csi_equity: list[float],
    variants: list[tuple[float, float]],
    *,
    cost_bps: int,
) -> dict[str, object]:
    years = sorted({str(row["date"])[:4] for row in rows})
    test_years = [year for year in years if int(year) >= int(years[0]) + 5]
    selections: list[dict[str, object]] = []
    stitched_dates: list[str] = []
    stitched_equity = [1.0]
    stitched_csi = [1.0]
    stitched_start_date: str | None = None
    selected_counts: Counter[str] = Counter()

    for test_year in test_years:
        train_end = f"{int(test_year) - 1}1231"
        test_start = f"{test_year}0101"
        test_end = f"{test_year}1231"
        train_rows, train_csi = _slice_inputs(rows, csi_equity, end=train_end)
        test_indices = [
            index
            for index, row in enumerate(rows)
            if test_start <= str(row["date"]) <= test_end
        ]
        if len(train_rows) < TRADING_DAYS * 4 or not test_indices or test_indices[0] == 0:
            continue
        candidates: list[dict[str, object]] = []
        for threshold_scale, exposure_scale in variants:
            result = _simulate(
                train_rows,
                train_csi,
                threshold_scale=threshold_scale,
                exposure_scale=exposure_scale,
                cost_bps=cost_bps,
            )
            metrics = dict(_mapping(result["metrics"]))
            if float(metrics.get("max_drawdown") or -1.0) >= -0.45:
                candidates.append(metrics)
        if not candidates:
            continue
        selected = max(candidates, key=_rank_key)
        threshold_scale = float(selected["threshold_scale"])
        exposure_scale = float(selected["exposure_scale"])
        context_start = test_indices[0] - 1
        context_end = test_indices[-1] + 1
        test_rows = rows[context_start:context_end]
        test_base = csi_equity[context_start]
        test_csi = [value / test_base for value in csi_equity[context_start:context_end]]
        test_result = _simulate(
            test_rows,
            test_csi,
            threshold_scale=threshold_scale,
            exposure_scale=exposure_scale,
            cost_bps=cost_bps,
        )
        test_metrics = dict(_mapping(test_result["metrics"]))
        selected_id = str(selected["variant_id"])
        selected_counts[selected_id] += 1
        selections.append(
            {
                "test_year": test_year,
                "training_start": str(train_rows[0]["date"]),
                "training_end": str(train_rows[-1]["date"]),
                "selected_variant": selected_id,
                "training_calmar": selected.get("calmar"),
                "training_CAGR": selected.get("CAGR"),
                "test_CAGR": test_metrics.get("CAGR"),
                "test_max_drawdown": test_metrics.get("max_drawdown"),
                "test_calmar": test_metrics.get("calmar"),
            }
        )
        test_equity = list(test_result["equity"])
        if stitched_start_date is None:
            stitched_start_date = str(test_rows[0]["date"])
        for index in range(1, len(test_equity)):
            stitched_equity.append(stitched_equity[-1] * (test_equity[index] / test_equity[index - 1]))
            stitched_csi.append(stitched_csi[-1] * (test_csi[index] / test_csi[index - 1]))
            stitched_dates.append(str(test_rows[index]["date"]))

    if stitched_dates:
        dates_for_metrics = [str(stitched_start_date)] + stitched_dates
        combined = _metrics(dates_for_metrics, stitched_equity, benchmark_cagr=_metrics(dates_for_metrics, stitched_csi).get("CAGR"))
        csi_metrics = _metrics(dates_for_metrics, stitched_csi)
    else:
        combined = _metrics([], [])
        csi_metrics = _metrics([], [])
    return {
        "selection_rule": "Use only prior data; choose highest training Calmar, then CAGR, then shallower drawdown; reject max drawdown below -45%.",
        "minimum_training_years": 5,
        "test_horizon": "next calendar year",
        "cost_bps": cost_bps,
        "selections": selections,
        "selected_variant_counts": dict(sorted(selected_counts.items())),
        "unique_selected_variants": len(selected_counts),
        "combined_oos_metrics": combined,
        "combined_oos_csi_300_metrics": csi_metrics,
    }


def validate_v15_macro_drawdown_robustness_result(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    grid = payload.get("parameter_grid")
    walk_forward = _mapping(payload.get("walk_forward"))
    constraints = _mapping(payload.get("constraints"))
    if payload.get("phase") != "V15.4":
        raise AssertionError("phase must be V15.4")
    if payload.get("validation_status") != "completed":
        raise AssertionError("validation_status must be completed")
    for key in ("research_backtest_only", "not_production_signal", "no_real_trade_order", "uses_t_plus_one_execution"):
        if payload.get(key) is not True:
            raise AssertionError(f"{key} must be true")
    if not isinstance(grid, list) or len(grid) != len(THRESHOLD_SCALES) * len(EXPOSURE_SCALES):
        raise AssertionError("parameter grid must contain nine variants")
    if not walk_forward.get("selections"):
        raise AssertionError("walk-forward selections are required")
    if summary.get("strict_point_in_time_status") != "unverified":
        raise AssertionError("strict point-in-time status must remain unverified")
    for key in ("no_broker_connection", "no_order_generation", "not_intraday_signal", "not_production_trade_signal"):
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    return {
        "audit_status": "passed",
        "checked_phase": payload.get("phase"),
        "checked_grid_variants": len(grid),
        "checked_walk_forward_years": len(walk_forward.get("selections") or []),
        "checked_strict_point_in_time_status": summary.get("strict_point_in_time_status"),
        "checked_no_real_trade_order": payload.get("no_real_trade_order"),
    }


def build_v15_macro_drawdown_robustness_result(
    *,
    input_path: str | Path = DEFAULT_INPUT_PATH,
) -> dict[str, object]:
    source = _read_json(input_path)
    if source.get("phase") != "V15.3" or source.get("backtest_status") != "completed":
        raise RuntimeError("V15.4 requires the completed V15.3 backtest artifact.")

    curves = _build_curves()
    rows = [dict(_mapping(row)) for row in curves["curve"]]
    csi_equity = [float(value) for value in curves["csi_equity"]]
    variants = [(threshold, exposure) for threshold in THRESHOLD_SCALES for exposure in EXPOSURE_SCALES]
    grid: list[dict[str, object]] = []
    for threshold_scale, exposure_scale in variants:
        simulated = _simulate(
            rows,
            csi_equity,
            threshold_scale=threshold_scale,
            exposure_scale=exposure_scale,
            cost_bps=TRANSACTION_COST_BPS,
        )
        grid.append(dict(_mapping(simulated["metrics"])))
    grid.sort(key=_rank_key, reverse=True)

    default = next(item for item in grid if item["variant_id"] == "t100_e100")
    source_strategy = _mapping(_mapping(source.get("strategy_results")).get("macro_drawdown_strategy"))
    reproduction_error = abs(float(default["CAGR"]) - float(source_strategy.get("CAGR") or 0.0))
    default_rank = next(index for index, item in enumerate(grid, start=1) if item["variant_id"] == "t100_e100")
    cagr_values = sorted(float(item["CAGR"]) for item in grid)
    calmar_values = sorted(float(item["calmar"] or 0.0) for item in grid)

    walk_forward_by_cost = {
        str(cost): _walk_forward(rows, csi_equity, variants, cost_bps=cost)
        for cost in COST_BPS_LEVELS
    }
    default_cost_sensitivity: dict[str, dict[str, object]] = {}
    for cost in COST_BPS_LEVELS:
        result = _simulate(rows, csi_equity, threshold_scale=1.0, exposure_scale=1.0, cost_bps=cost)
        default_cost_sensitivity[str(cost)] = dict(_mapping(result["metrics"]))

    primary_cost_key = str(TRANSACTION_COST_BPS)
    primary_oos = _mapping(walk_forward_by_cost[primary_cost_key]).get("combined_oos_metrics")
    primary_oos_metrics = _mapping(primary_oos)
    primary_oos_csi = _mapping(_mapping(walk_forward_by_cost[primary_cost_key]).get("combined_oos_csi_300_metrics"))
    stable_grid = max(cagr_values) - min(cagr_values) <= 0.02 and max(calmar_values) - min(calmar_values) <= 0.15
    default_parameter_preferred = default_rank <= 3
    oos_beats_csi = float(primary_oos_metrics.get("CAGR") or -1.0) > float(primary_oos_csi.get("CAGR") or -1.0)
    source_strategy = _mapping(_mapping(source.get("strategy_results")).get("macro_drawdown_strategy"))
    source_comparison = _mapping(source.get("comparison"))
    formal_checks = {
        "full_period_beats_total_return_benchmark": source_comparison.get("beats_csi_300_buy_hold") is True,
        "full_period_annual_alpha_positive": float(source_strategy.get("annual_alpha") or 0.0) > 0.0,
        "full_period_max_drawdown_within_30pct": float(source_strategy.get("max_drawdown") or -1.0) >= -0.30,
        "out_of_sample_beats_total_return_benchmark": oos_beats_csi,
        "out_of_sample_beats_cash": float(primary_oos_metrics.get("CAGR") or -1.0) > CASH_ANNUAL_RETURN,
        "default_parameter_rank_in_top_three": default_parameter_preferred,
        "strict_point_in_time_verified": False,
    }
    formal_evaluation_passed = all(formal_checks.values())
    strict_point_in_time_verified = False
    promotion_ready = stable_grid and default_parameter_preferred and oos_beats_csi and strict_point_in_time_verified
    conclusion = (
        "The 2016+ total-return evaluation with 15bp one-way costs does not beat CSI300 total return over the full period, "
        "out-of-sample CAGR remains below cash, and strict point-in-time phase history is unverified; reject promotion."
    )

    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.4 Macro + Drawdown Robustness And Walk-Forward Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": rows[-1]["date"],
            "source_backtest": "data/v15_macro_drawdown_backtest_result.json",
            "purpose": "Test whether V15.3 survives nearby parameters, transaction costs, and prior-data-only annual walk-forward selection.",
        },
        "phase": "V15.4",
        "validation_status": "completed",
        "research_backtest_only": True,
        "not_production_signal": True,
        "no_real_trade_order": True,
        "uses_t_plus_one_execution": True,
        "summary": {
            "phase": "V15.4",
            "validation_status": "completed",
            "parameter_variants": len(grid),
            "default_variant_rank": default_rank,
            "default_CAGR": default.get("CAGR"),
            "best_CAGR": max(cagr_values),
            "worst_CAGR": min(cagr_values),
            "CAGR_range": round(max(cagr_values) - min(cagr_values), 6),
            "default_calmar": default.get("calmar"),
            "calmar_range": round(max(calmar_values) - min(calmar_values), 6),
            "default_reproduction_CAGR_error": round(reproduction_error, 8),
            "walk_forward_cost_bps": TRANSACTION_COST_BPS,
            "walk_forward_CAGR": primary_oos_metrics.get("CAGR"),
            "walk_forward_max_drawdown": primary_oos_metrics.get("max_drawdown"),
            "walk_forward_calmar": primary_oos_metrics.get("calmar"),
            "walk_forward_beats_csi_300": oos_beats_csi,
            "parameter_neighborhood_stable": stable_grid,
            "default_parameter_preferred": default_parameter_preferred,
            "promotion_ready": promotion_ready,
            "formal_evaluation_status": "passed" if formal_evaluation_passed else "failed",
            "strict_point_in_time_status": "unverified",
            "research_backtest_only": True,
            "no_real_trade_order": True,
            "conclusion": conclusion,
            "next_task": "Verify point-in-time phase history and test valuation/crowding late-cycle overlay before promotion.",
        },
        "parameter_design": {
            "threshold_scales": list(THRESHOLD_SCALES),
            "exposure_scales": list(EXPOSURE_SCALES),
            "exposure_scaling": "Scale each V15.3 exposure around neutral 0.50, clipped to [0, 1].",
            "cost_bps_levels": list(COST_BPS_LEVELS),
            "primary_evaluation_cost_bps": TRANSACTION_COST_BPS,
            "signal_timing": "phase and drawdown observed after close on t; selected exposure applied to t+1 return",
        },
        "parameter_grid": grid,
        "default_cost_sensitivity": default_cost_sensitivity,
        "walk_forward": walk_forward_by_cost[primary_cost_key],
        "walk_forward_cost_sensitivity": walk_forward_by_cost,
        "formal_evaluation": {
            "status": "passed" if formal_evaluation_passed else "failed",
            "decision": "promote" if formal_evaluation_passed else "reject_promotion",
            "evaluation_window": "2016 onward",
            "signal_index": "000300.SH",
            "return_and_benchmark_index": "H00300.CSI",
            "transaction_cost_bps": TRANSACTION_COST_BPS,
            "checks": formal_checks,
            "conclusion": conclusion,
        },
        "data_quality": {
            "source_phase": source.get("phase"),
            "source_backtest_status": source.get("backtest_status"),
            "source_sessions": len(rows),
            "default_reproduction_within_tolerance": reproduction_error <= 0.0001,
            "t_plus_one_reapplied_for_every_variant": True,
            "training_uses_only_dates_before_test_year": True,
            "phase_history_strict_point_in_time_not_independently_verified": True,
            "point_in_time_caveat": "market_phase_snapshot historical replay may be reconstructed; publication-time lineage is not proven by V15.4.",
        },
        "constraints": {
            "no_broker_connection": True,
            "no_order_generation": True,
            "not_intraday_signal": True,
            "not_production_trade_signal": True,
            "no_current_position_recommendation": True,
        },
    }
    payload["audit"] = validate_v15_macro_drawdown_robustness_result(payload)
    return payload


def write_v15_macro_drawdown_robustness_result(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    validate_v15_macro_drawdown_robustness_result(payload)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
