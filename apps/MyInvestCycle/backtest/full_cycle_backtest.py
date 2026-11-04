from __future__ import annotations

from bisect import bisect_right
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot
from backtest.allocation_backtest_engine import run_v2_allocation_backtest
from backtest.benchmark_comparator import metrics_for_returns
from backtest.full_cycle_validation import (
    _display_path,
    _signal_history_snapshot_builder,
    build_data_coverage_audit,
)
from config import BREADTH_HISTORY_SAMPLE_SIZE, CACHE_DIR, DATA_DIR
from core.alpha_validation_engine import compound_return
from core.breadth import calculate_breadth_metrics, get_market_daily, get_market_history_sample
from core.data_loader import cache_path_for, normalize_trade_date
from core.liquidity import HSGT_COLUMNS, calculate_liquidity_metrics
from industry_structure.industry_loader import load_industry_panel
from industry_structure.opportunity_engine import _explain as _explain_industry
from industry_structure.opportunity_engine import _latest_common_as_of, _top_themes
from macro.macro_cycle_engine import build_macro_cycle_snapshot
from market_structure.structure_classifier import classify_structure, estimate_structure_confidence
from market_structure.structure_engine import DEFAULT_INDEX_CODES
from market_structure.structure_explainer import explain_structure
from market_structure.structure_score_engine import INDEX_LABELS, build_structure_metrics, score_index_trend
from structural_bull.structural_bull_engine import build_structural_bull_snapshot
from theme_risk.crowding_risk_engine import evaluate_crowding_risk
from theme_risk.opportunity_quality_engine import _risk_level, _warning_union
from theme_risk.valuation_pressure_engine import evaluate_valuation_pressure


DEFAULT_OUTPUT_PATH = DATA_DIR / "v2_full_cycle_backtest.json"
SNAPSHOT_MANIFEST_PATH = DATA_DIR / "history_snapshots" / "v2_full_cycle_backtest_manifest.json"
SIGNAL_SNAPSHOT_PATH = DATA_DIR / "history_snapshots" / "v2_full_cycle_backtest_rebalance_signals.json"

TARGET_START = "20150105"
TARGET_END = "20991231"
WARMUP_START = "20130101"
MACRO_START = "20140101"
SOFT_MACRO_GAPS = ("CN10Y", "new_loans")
MACRO_CONFIDENCE_PENALTY = 0.10

PHASES: tuple[dict[str, str], ...] = (
    {"phase_id": "2015_bull_bear", "label": "2015 牛熊", "start": "20150105", "end": "20151231"},
    {"phase_id": "2018_bear", "label": "2018 熊市", "start": "20180101", "end": "20181231"},
    {"phase_id": "2020_covid", "label": "2020 疫情冲击", "start": "20200101", "end": "20201231"},
    {"phase_id": "2021_core_asset", "label": "2021 抱团分化", "start": "20210101", "end": "20211231"},
    {"phase_id": "2022_bear", "label": "2022 熊市", "start": "20220101", "end": "20221231"},
    {"phase_id": "2024_2026_structural", "label": "2024-2026 结构行情", "start": "20240101", "end": "20260708"},
)

STRATEGY_COLUMNS: dict[str, dict[str, object]] = {
    "v2_current": {
        "label": "V2 现行规则",
        "column": "v2_return",
        "exposure_column": "target_exposure",
        "turnover_column": "turnover",
        "coverage": "full",
        "same_series_as": "v2_structural_refined",
    },
    "v2_structural_refined": {
        "label": "V2 structural refined",
        "column": "v2_return",
        "exposure_column": "target_exposure",
        "turnover_column": "turnover",
        "coverage": "full",
        "same_series_as": "v2_current",
    },
    "v2_baseline": {
        "label": "V2 baseline",
        "column": "v2_baseline_return",
        "exposure_column": "v2_baseline_exposure",
        "turnover_column": "v2_baseline_turnover",
        "coverage": "full",
    },
    "benchmark_510300": {
        "label": "510300 沪深300ETF",
        "column": "benchmark_510300_return",
        "coverage": "full",
        "fixed_exposure": 1.0,
        "fixed_turnover": 0.0,
    },
    "benchmark_510500": {
        "label": "510500 中证500ETF",
        "column": "benchmark_510500_return",
        "coverage": "full",
        "fixed_exposure": 1.0,
        "fixed_turnover": 0.0,
    },
    "buy_hold_equal_510300_510500": {
        "label": "50/50 Buy&Hold",
        "column": "buy_hold_equal_return",
        "coverage": "full",
        "fixed_exposure": 1.0,
        "fixed_turnover": 0.0,
    },
    "old_s1": {
        "label": "S1.1 仓位风控",
        "column": "old_s1_actual_return",
        "coverage": "partial_artifact",
    },
    "m2_macro_style": {
        "label": "M2.1 Macro-Style-ETF",
        "column": "m2_actual_return",
        "coverage": "partial_artifact",
    },
}


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _round(value: object, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _read_index_cache(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = cache_path_for(code)
    if not path.exists():
        raise FileNotFoundError(f"index cache missing for {code}: {path}")
    frame = pd.read_csv(path, dtype={"trade_date": str})
    frame["trade_date"] = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    return frame[(frame["trade_date"] >= start_date) & (frame["trade_date"] <= end_date)].sort_values("trade_date").reset_index(drop=True)


def _load_hsgt_cache() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(CACHE_DIR.glob("moneyflow_hsgt_*.csv")):
        frame = pd.read_csv(path, dtype={"trade_date": str})
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=HSGT_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    for column in HSGT_COLUMNS:
        if column not in combined:
            combined[column] = pd.NA
    combined = combined[HSGT_COLUMNS]
    combined["trade_date"] = combined["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    for column in HSGT_COLUMNS:
        if column != "trade_date":
            combined[column] = pd.to_numeric(combined[column], errors="coerce")
    return combined.drop_duplicates(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)


def _filter_frame(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result = frame[(dates >= start_date) & (dates <= end_date)].copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    return result.sort_values("trade_date").reset_index(drop=True)


def _price_history_tuple(frame: pd.DataFrame) -> tuple[list[str], list[float]]:
    if frame.empty:
        return [], []
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["trade_date", "close"]).sort_values("trade_date")
    return result["trade_date"].astype(str).tolist(), result["close"].astype(float).tolist()


class HistoricalAllocationSnapshotBuilder:
    """Cache input histories once; every snapshot still slices only data visible by as_of."""

    def __init__(
        self,
        *,
        warmup_start: str,
        macro_start: str,
        end_date: str,
        cache_only: bool = True,
    ) -> None:
        self.warmup_start = normalize_trade_date(warmup_start)
        self.macro_start = normalize_trade_date(macro_start)
        self.end_date = normalize_trade_date(end_date)
        self.cache_only = cache_only
        self.index_frames = {
            code: _read_index_cache(code, self.warmup_start, self.end_date)
            for code in DEFAULT_INDEX_CODES
        }
        self.hsgt = _load_hsgt_cache()
        self.assets, self.industry_frames, self.industry_status = load_industry_panel(
            self.warmup_start,
            self.end_date,
            cache_only=cache_only,
            refresh_universe=False,
            refresh_prices=False,
        )
        self.asset_map = {asset.code: asset for asset in self.assets}
        self.benchmark_frames = {
            code: _read_index_cache(code, self.warmup_start, self.end_date)
            for code in ("000300.SH", "000905.SH")
        }
        self.industry_history = {
            code: _price_history_tuple(frame)
            for code, frame in self.industry_frames.items()
        }
        self.benchmark_history = {
            code: _price_history_tuple(frame)
            for code, frame in self.benchmark_frames.items()
        }
        all_dates: set[str] = set()
        for dates, _ in self.industry_history.values():
            all_dates.update(dates)
        self.industry_dates = sorted(all_dates)

    def _structure_snapshot(self, as_of: str) -> dict[str, object]:
        requested_as_of = normalize_trade_date(as_of)
        frames = {
            code: _filter_frame(frame, self.warmup_start, requested_as_of)
            for code, frame in self.index_frames.items()
        }
        frames = {code: frame for code, frame in frames.items() if not frame.empty}
        if not frames:
            raise ValueError("No index frames available for historical structure snapshot.")
        resolved_as_of = min(str(frame["trade_date"].iloc[-1]) for frame in frames.values())
        aligned = {code: frame[frame["trade_date"] <= resolved_as_of].copy() for code, frame in frames.items()}
        index_metrics = {
            code: {
                "label": INDEX_LABELS.get(code, code),
                **score_index_trend(frame),
            }
            for code, frame in aligned.items()
        }
        market_daily = get_market_daily(resolved_as_of)
        market_history = get_market_history_sample(
            market_daily,
            _calendar_shift(resolved_as_of, -370),
            resolved_as_of,
            sample_size=BREADTH_HISTORY_SAMPLE_SIZE,
        )
        breadth_metrics = calculate_breadth_metrics(market_daily, market_history_df=market_history)
        hsgt = _filter_frame(self.hsgt, _calendar_shift(resolved_as_of, -45), resolved_as_of)
        try:
            liquidity_metrics = calculate_liquidity_metrics(aligned[DEFAULT_INDEX_CODES[0]], hsgt_df=hsgt)
            liquidity_status: dict[str, object] = {
                "status": "available" if not hsgt.empty else "fallback_to_turnover",
                "rows": int(len(hsgt)),
            }
        except Exception as exc:
            liquidity_metrics = None
            liquidity_status = {"status": "missing", "message": str(exc)}
        metrics = build_structure_metrics(
            index_metrics,
            breadth_metrics=breadth_metrics,
            liquidity_metrics=liquidity_metrics,
            industry_metrics=None,
        )
        state = classify_structure(metrics)
        confidence = estimate_structure_confidence(metrics, state)
        return {
            "engine": "V2.3.1 Market Structure Engine Core",
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "structure_state": state,
            "structure_score": metrics["structure_score"],
            "confidence": confidence,
            "metrics": metrics,
            "index_metrics": index_metrics,
            "data_quality": {
                "index_codes": list(aligned),
                "breadth": {
                    "status": "available",
                    "market_daily_rows": int(len(market_daily)),
                    "history": {"status": "available", "rows": int(len(market_history))},
                },
                "liquidity": liquidity_status,
                "industry_theme_data": "not_available_in_v2_3_1",
                "no_future_data": resolved_as_of <= requested_as_of,
            },
            "explanation": explain_structure(state, metrics),
            "constraints": {
                "independent_from_macro_state": True,
                "no_position_sizing": True,
                "no_etf_allocation": True,
                "no_trade_signal": True,
                "no_backtest": True,
            },
        }

    def _industry_snapshot(self, as_of: str) -> dict[str, object]:
        requested_as_of = normalize_trade_date(as_of)
        frames = {
            code: _filter_frame(frame, self.warmup_start, requested_as_of)
            for code, frame in self.industry_frames.items()
        }
        frames = {code: frame for code, frame in frames.items() if not frame.empty}
        benchmark_frames = {
            code: _filter_frame(frame, self.warmup_start, requested_as_of)
            for code, frame in self.benchmark_frames.items()
        }
        benchmark_frames = {code: frame for code, frame in benchmark_frames.items() if not frame.empty}
        if not frames:
            raise ValueError("No industry histories available for historical opportunity snapshot.")
        if not benchmark_frames:
            raise ValueError("No benchmark histories available for historical opportunity snapshot.")
        resolved_as_of = _latest_common_as_of(requested_as_of, frames, benchmark_frames)
        strength = self._industry_strength(resolved_as_of)
        persistence = self._theme_persistence(resolved_as_of)
        top_themes = _top_themes(
            list(strength.get("industries") or []),
            list(persistence.get("persistence_by_industry") or []),
        )
        industry_strength = float(strength.get("industry_strength") or 0.0)
        theme_persistence = float(persistence.get("theme_persistence_score") or 0.0)
        rotation_health = float(strength.get("rotation_health") or 0.0)
        opportunity_score = 0.42 * industry_strength + 0.38 * theme_persistence + 0.20 * rotation_health
        source_type = str(self.industry_status.get("source_type") or "unknown")
        payload: dict[str, object] = {
            "engine": "V2.3.2 Industry / Theme Opportunity Engine",
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_type": source_type,
            "industry_opportunity_score": round(opportunity_score, 4),
            "industry_strength": round(industry_strength, 4),
            "theme_persistence": round(theme_persistence, 4),
            "top_themes": top_themes,
            "metrics": {
                "industry_breadth": strength.get("industry_breadth"),
                "positive_industry_ratio": strength.get("positive_industry_ratio"),
                "top_industry_ratio": strength.get("top_industry_ratio"),
                "rotation_health": strength.get("rotation_health"),
                "theme_persistence_score": persistence.get("theme_persistence_score"),
                "ranking_observations": persistence.get("ranking_observations"),
            },
            "benchmark_returns": strength.get("benchmark_returns"),
            "industries": strength.get("industries"),
            "persistence_by_industry": persistence.get("persistence_by_industry"),
            "data_quality": {
                "industry_status": self.industry_status,
                "benchmark_status": {
                    "benchmark_codes": list(benchmark_frames),
                    "available_count": len(benchmark_frames),
                    "errors": {},
                },
                "no_future_data": resolved_as_of <= requested_as_of,
            },
            "constraints": {
                "no_etf_allocation": True,
                "no_position_sizing": True,
                "no_trade_signal": True,
                "no_backtest": True,
            },
        }
        payload["explanation"] = _explain_industry(payload)
        return payload

    def _trailing_return(self, history: tuple[list[str], list[float]], as_of: str, window: int) -> float | None:
        dates, closes = history
        position = bisect_right(dates, as_of) - 1
        if position < window:
            return None
        latest = float(closes[position])
        previous = float(closes[position - window])
        if previous <= 0:
            return None
        return latest / previous - 1.0

    def _benchmark_returns(self, as_of: str) -> dict[str, object]:
        by_code: dict[str, dict[str, float | None]] = {}
        average: dict[str, float | None] = {}
        for code, history in self.benchmark_history.items():
            by_code[code] = {
                f"return_{window}d": self._trailing_return(history, as_of, window)
                for window in (5, 20, 60)
            }
        for window in (5, 20, 60):
            values = [
                float(metrics[f"return_{window}d"])
                for metrics in by_code.values()
                if metrics.get(f"return_{window}d") is not None
            ]
            average[f"return_{window}d"] = sum(values) / len(values) if values else None
        return {"by_code": by_code, "average": average}

    def _industry_strength(self, as_of: str) -> dict[str, object]:
        benchmark = self._benchmark_returns(as_of)
        benchmark_average = benchmark["average"]
        rows: list[dict[str, object]] = []
        for code, history in self.industry_history.items():
            asset = self.asset_map.get(code)
            if asset is None:
                continue
            returns = {f"return_{window}d": self._trailing_return(history, as_of, window) for window in (5, 20, 60)}
            if returns["return_60d"] is None or returns["return_20d"] is None:
                continue
            relative_60d = None
            if benchmark_average.get("return_60d") is not None:
                relative_60d = float(returns["return_60d"]) - float(benchmark_average["return_60d"])
            rows.append(
                {
                    "code": code,
                    "name": asset.name,
                    "source_type": asset.source_type,
                    **returns,
                    "relative_60d": relative_60d,
                }
            )

        table = pd.DataFrame(rows)
        if table.empty:
            return {
                "as_of": as_of,
                "benchmark_returns": benchmark,
                "industry_strength": 0.0,
                "industry_breadth": 0.0,
                "positive_industry_ratio": 0.0,
                "top_industry_ratio": 0.0,
                "rotation_health": 0.0,
                "industries": [],
            }

        for column in ["return_5d", "return_20d", "return_60d", "relative_60d"]:
            table[f"{column}_rank"] = pd.to_numeric(table[column], errors="coerce").rank(method="average", pct=True) * 100.0

        table["strength_score"] = (
            0.18 * table["return_5d_rank"].fillna(50.0)
            + 0.32 * table["return_20d_rank"].fillna(50.0)
            + 0.32 * table["return_60d_rank"].fillna(50.0)
            + 0.18 * table["relative_60d_rank"].fillna(50.0)
        )
        table = table.sort_values("strength_score", ascending=False).reset_index(drop=True)
        industry_count = len(table)
        top_count = min(5, industry_count)
        positive_ratio = float((pd.to_numeric(table["return_20d"], errors="coerce") > 0).mean())
        top_ratio = float((table["strength_score"] >= 70.0).mean())
        industry_breadth = float(
            (
                (pd.to_numeric(table["return_20d"], errors="coerce") > 0)
                & (pd.to_numeric(table["return_60d"], errors="coerce") > 0)
            ).mean()
        )
        top_avg = float(table.head(top_count)["strength_score"].mean())
        rotation_health = 0.50 * top_avg + 0.30 * positive_ratio * 100.0 + 0.20 * top_ratio * 100.0
        industry_strength = 0.62 * top_avg + 0.23 * industry_breadth * 100.0 + 0.15 * top_ratio * 100.0
        industries = []
        for _, row in table.iterrows():
            industries.append(
                {
                    "code": str(row["code"]),
                    "name": str(row["name"]),
                    "source_type": str(row["source_type"]),
                    "return_5d": None if pd.isna(row["return_5d"]) else round(float(row["return_5d"]), 6),
                    "return_20d": None if pd.isna(row["return_20d"]) else round(float(row["return_20d"]), 6),
                    "return_60d": None if pd.isna(row["return_60d"]) else round(float(row["return_60d"]), 6),
                    "relative_60d": None if pd.isna(row["relative_60d"]) else round(float(row["relative_60d"]), 6),
                    "rank_percentile": round(float(row["strength_score"]), 4),
                    "strength_score": round(float(row["strength_score"]), 4),
                }
            )
        return {
            "as_of": as_of,
            "benchmark_returns": benchmark,
            "industry_strength": round(industry_strength, 4),
            "industry_breadth": round(industry_breadth, 4),
            "positive_industry_ratio": round(positive_ratio, 4),
            "top_industry_ratio": round(top_ratio, 4),
            "rotation_health": round(rotation_health, 4),
            "industries": industries,
        }

    def _ranking_table_for_date(self, eval_date: str) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for code, history in self.industry_history.items():
            ret20 = self._trailing_return(history, eval_date, 20)
            ret60 = self._trailing_return(history, eval_date, 60)
            if ret20 is None or ret60 is None:
                continue
            rows.append({"code": code, "return_20d": ret20, "return_60d": ret60})
        table = pd.DataFrame(rows)
        if table.empty:
            return table
        table["rank20"] = table["return_20d"].rank(method="average", pct=True) * 100.0
        table["rank60"] = table["return_60d"].rank(method="average", pct=True) * 100.0
        table["rank_score"] = 0.45 * table["rank20"] + 0.55 * table["rank60"]
        table["eval_date"] = eval_date
        return table

    def _theme_persistence(self, as_of: str, lookback: int = 60) -> dict[str, object]:
        position = bisect_right(self.industry_dates, as_of)
        eval_dates = self.industry_dates[max(0, position - lookback):position]
        ranking_frames = [self._ranking_table_for_date(date_text) for date_text in eval_dates]
        ranking_frames = [frame for frame in ranking_frames if not frame.empty]
        if not ranking_frames:
            return {
                "as_of": as_of,
                "theme_persistence_score": 0.0,
                "persistence_by_industry": [],
                "ranking_observations": 0,
            }
        ranks = pd.concat(ranking_frames, ignore_index=True).sort_values(["code", "eval_date"])
        rows: list[dict[str, object]] = []
        for code, group in ranks.groupby("code"):
            asset = self.asset_map.get(str(code))
            if asset is None:
                continue
            group = group.sort_values("eval_date")
            last20 = group.tail(20)
            last40 = group.tail(40)
            last60 = group.tail(60)
            top20 = float((last20["rank_score"] >= 80.0).mean()) if not last20.empty else 0.0
            top40 = float((last40["rank_score"] >= 80.0).mean()) if not last40.empty else 0.0
            top60 = float((last60["rank_score"] >= 80.0).mean()) if not last60.empty else 0.0
            avg_rank60 = float(last60["rank_score"].mean()) if not last60.empty else 0.0
            latest_rank = float(group["rank_score"].iloc[-1])
            persistence_score = (
                0.30 * top20 * 100.0
                + 0.25 * top40 * 100.0
                + 0.20 * top60 * 100.0
                + 0.15 * avg_rank60
                + 0.10 * latest_rank
            )
            rows.append(
                {
                    "code": str(code),
                    "name": asset.name,
                    "source_type": asset.source_type,
                    "latest_rank": round(latest_rank, 4),
                    "top20_hit_ratio": round(top20, 4),
                    "top40_hit_ratio": round(top40, 4),
                    "top60_hit_ratio": round(top60, 4),
                    "avg_rank60": round(avg_rank60, 4),
                    "persistence_score": round(float(persistence_score), 4),
                }
            )
        rows = sorted(rows, key=lambda item: float(item["persistence_score"]), reverse=True)
        top_count = min(5, len(rows))
        persistence_score = sum(float(item["persistence_score"]) for item in rows[:top_count]) / top_count if top_count else 0.0
        return {
            "as_of": as_of,
            "theme_persistence_score": round(persistence_score, 4),
            "persistence_by_industry": rows,
            "ranking_observations": int(len(ranks)),
        }

    def _theme_risk_snapshot(self, as_of: str, industry_payload: Mapping[str, object]) -> dict[str, object]:
        requested_as_of = normalize_trade_date(as_of)
        resolved_as_of = str(industry_payload.get("as_of") or requested_as_of)
        top_themes = list(industry_payload.get("top_themes") or [])
        frames = {
            str(theme.get("code")): self.industry_frames[str(theme.get("code"))]
            for theme in top_themes
            if str(theme.get("code")) in self.industry_frames
        }
        valuation_items = evaluate_valuation_pressure(top_themes, frames, resolved_as_of)
        crowding = evaluate_crowding_risk(industry_payload, valuation_items)
        opportunity_score = float(industry_payload.get("industry_opportunity_score") or 0.0)
        theme_persistence = float(industry_payload.get("theme_persistence") or 0.0)
        crowding_score = float(crowding["crowding_score"])
        quality_score = 0.45 * opportunity_score + 0.25 * theme_persistence + 0.30 * (100.0 - crowding_score)
        valuation_warnings = _warning_union(*[list(item.get("warnings") or []) for item in valuation_items])
        warnings = _warning_union(valuation_warnings, list(crowding.get("warnings") or []))
        risk_level = _risk_level(crowding_score, quality_score)
        top_theme = top_themes[0] if top_themes else {}
        return {
            "engine": "V2.3.4 Theme Valuation & Crowding Risk Layer",
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "theme_risk_level": risk_level,
            "quality_score": round(quality_score, 4),
            "crowding_score": round(crowding_score, 4),
            "top_theme": {
                "code": top_theme.get("code"),
                "name": top_theme.get("name"),
                "composite_score": top_theme.get("composite_score"),
            },
            "warnings": warnings,
            "valuation_pressure": valuation_items,
            "crowding": crowding,
            "input_summary": {
                "industry_opportunity_score": industry_payload.get("industry_opportunity_score"),
                "industry_strength": industry_payload.get("industry_strength"),
                "theme_persistence": industry_payload.get("theme_persistence"),
                "industry_source_type": industry_payload.get("source_type"),
                "top_theme_count": len(top_themes),
            },
            "data_quality": {
                "theme_frames": {
                    "requested_codes": [str(theme.get("code")) for theme in top_themes],
                    "available_count": len(frames),
                    "errors": {},
                },
                "industry_as_of": industry_payload.get("as_of"),
                "no_future_data": resolved_as_of <= requested_as_of,
                "valuation_is_price_position_proxy": True,
            },
            "explanation": [
                "本层只判断主线机会是否过热或拥挤，不改变 Structural Bull 状态。",
                "valuation_pressure 使用价格位置、均线偏离和短中期涨幅做代理，不是 PE/PB 等基本面估值。",
                f"当前风险等级 {risk_level}，quality_score={quality_score:.1f}，crowding_score={crowding_score:.1f}。",
                "V2.3.4 不输出仓位、ETF 配置、买卖建议或回测结论。",
            ],
            "constraints": {
                "does_not_change_structural_bull_state": True,
                "no_etf_allocation": True,
                "no_position_sizing": True,
                "no_trade_signal": True,
                "no_backtest": True,
                "quality_filter_only": True,
            },
        }

    def __call__(self, date_text: str) -> Mapping[str, object]:
        macro = build_macro_cycle_snapshot(date_text, start_date=self.macro_start)
        structure = self._structure_snapshot(date_text)
        industry = self._industry_snapshot(date_text)
        structural = build_structural_bull_snapshot(
            date_text,
            macro_payload=macro,
            structure_payload=structure,
            industry_payload=industry,
            cache_only=self.cache_only,
        )
        theme_risk = self._theme_risk_snapshot(date_text, industry)
        return build_allocation_intent_snapshot(
            date_text,
            structural_payload=structural,
            theme_risk_payload=theme_risk,
            cache_only=self.cache_only,
        )


def _frame_from_payload(payload: Mapping[str, object], *, prefix: str | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(payload.get("daily_returns") or [])
    if frame.empty:
        return frame
    frame = frame.sort_values("date").reset_index(drop=True)
    for column in frame.columns:
        if column.endswith("_return") or column in {"turnover", "target_exposure"}:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if prefix:
        rename = {
            "v2_return": f"{prefix}_return",
            "target_exposure": f"{prefix}_exposure",
            "turnover": f"{prefix}_turnover",
            "risk_budget": f"{prefix}_risk_budget",
        }
        frame = frame.rename(columns={key: value for key, value in rename.items() if key in frame})
    return frame


def _artifact_return_series(path: Path, row_key: str, value_key: str) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(row_key) or []
    values = {
        str(row.get("date")): float(row.get(value_key, 0.0))
        for row in rows
        if isinstance(row, Mapping) and row.get("date")
    }
    if not values:
        return pd.Series(dtype=float)
    return pd.Series(values, dtype=float).sort_index()


def _attach_partial_series(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    s1 = _artifact_return_series(DATA_DIR / "shadow_equity_curve.json", "shadow_returns", "return")
    m2 = _artifact_return_series(DATA_DIR / "macro_style_etf_backtest.json", "daily_returns", "hierarchical_return")
    result["old_s1_actual_return"] = result["date"].map(s1).astype(float)
    result["m2_actual_return"] = result["date"].map(m2).astype(float)
    return result


def _series_metrics(series: pd.Series) -> dict[str, object]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {
            "sessions": 0,
            "total_return": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe": None,
            "max_drawdown": None,
            "calmar": None,
        }
    return metrics_for_returns(clean)


def _coverage_for_series(frame: pd.DataFrame, column: str) -> dict[str, object]:
    if column not in frame:
        return {"start": None, "end": None, "sessions": 0, "coverage_ratio": 0.0}
    rows = frame[frame[column].notna()]
    return {
        "start": str(rows["date"].iloc[0]) if not rows.empty else None,
        "end": str(rows["date"].iloc[-1]) if not rows.empty else None,
        "sessions": int(len(rows)),
        "coverage_ratio": round(float(len(rows) / len(frame)), 6) if len(frame) else 0.0,
    }


def _comparison_table(frame: pd.DataFrame, refined: Mapping[str, object], legacy: Mapping[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for key, spec in STRATEGY_COLUMNS.items():
        column = str(spec["column"])
        metrics = _series_metrics(frame[column]) if column in frame else _series_metrics(pd.Series(dtype=float))
        exposure_column = spec.get("exposure_column")
        turnover_column = spec.get("turnover_column")
        exposure = spec.get("fixed_exposure")
        average_turnover = spec.get("fixed_turnover")
        cumulative_turnover = spec.get("fixed_turnover")
        if exposure_column and str(exposure_column) in frame:
            exposure = _round(pd.to_numeric(frame[str(exposure_column)], errors="coerce").dropna().mean())
        if turnover_column and str(turnover_column) in frame:
            turnover = pd.to_numeric(frame[str(turnover_column)], errors="coerce").fillna(0.0)
            average_turnover = _round(turnover.mean())
            cumulative_turnover = _round(turnover.sum())
        if key == "old_s1":
            shadow = json.loads((DATA_DIR / "shadow_equity_curve.json").read_text(encoding="utf-8")) if (DATA_DIR / "shadow_equity_curve.json").exists() else {}
            exposure = shadow.get("summary", {}).get("average_applied_exposure")
        if key == "m2_macro_style":
            m2 = json.loads((DATA_DIR / "macro_style_etf_backtest.json").read_text(encoding="utf-8")) if (DATA_DIR / "macro_style_etf_backtest.json").exists() else {}
            summary = m2.get("summary", {})
            exposure = summary.get("average_target_exposure")
            average_turnover = summary.get("average_turnover")
            cumulative_turnover = summary.get("cumulative_turnover")
        row = {
            "label": spec["label"],
            **metrics,
            "average_exposure": _round(exposure),
            "average_turnover": _round(average_turnover),
            "cumulative_turnover": _round(cumulative_turnover),
            "coverage": _coverage_for_series(frame, column),
            "coverage_type": spec.get("coverage"),
        }
        if spec.get("same_series_as"):
            row["same_series_as"] = spec["same_series_as"]
            row["note"] = "现行 V2 已内置 structural refined policy，因此两列使用同一条现行规则曲线。"
        result[key] = row
    result["v2_current"]["source_summary"] = refined.get("summary", {})
    result["v2_baseline"]["source_summary"] = legacy.get("summary", {})
    return result


def _phase_attribution(frame: pd.DataFrame) -> dict[str, object]:
    phases: dict[str, object] = {}
    for phase in PHASES:
        start = phase["start"]
        end = phase["end"]
        subset = frame[(frame["date"] >= start) & (frame["date"] <= end)].copy()
        strategies: dict[str, object] = {}
        for key, spec in STRATEGY_COLUMNS.items():
            column = str(spec["column"])
            strategies[key] = _series_metrics(subset[column]) if column in subset else _series_metrics(pd.Series(dtype=float))
            strategies[key]["coverage"] = _coverage_for_series(subset, column) if column in subset else {
                "start": None,
                "end": None,
                "sessions": 0,
                "coverage_ratio": 0.0,
            }
        phases[phase["phase_id"]] = {
            "label": phase["label"],
            "window": {"start": start, "end": end},
            "sessions": int(len(subset)),
            "strategies": strategies,
        }
    return phases


def _structural_bull_contribution(frame: pd.DataFrame) -> dict[str, object]:
    if "structural_state" not in frame:
        subset = frame.iloc[0:0]
    else:
        subset = frame[frame["structural_state"] == "STRUCTURAL_BULL_ROTATION"].copy()
    strategy_return = compound_return(subset["v2_return"]) if not subset.empty else 0.0
    benchmark_return = compound_return(subset["benchmark_510500_return"]) if not subset.empty else 0.0
    return {
        "STRUCTURAL_BULL_ROTATION": {
            "sessions": int(len(subset)),
            "average_exposure": _round(subset["target_exposure"].mean()) if not subset.empty else None,
            "return_contribution": _round(subset["v2_return"].sum()) if not subset.empty else 0.0,
            "compound_return_within_sessions": _round(strategy_return),
            "benchmark_510500_return": _round(benchmark_return),
            "missed_beta": _round(benchmark_return - strategy_return),
            "missed_beta_reference": "benchmark_510500_return - v2_return inside STRUCTURAL_BULL_ROTATION sessions",
        }
    }


def _equity_curve_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "date",
        "v2_current_equity",
        "v2_baseline_equity",
        "benchmark_510300_equity",
        "benchmark_510500_equity",
        "buy_hold_equal_equity",
        "old_s1_actual_equity",
        "m2_actual_equity",
        "target_exposure",
        "v2_baseline_exposure",
        "structural_state",
        "allocation_structural_state",
    ]
    rows: list[dict[str, object]] = []
    for _, row in frame[columns].iterrows():
        item: dict[str, object] = {}
        for column in columns:
            value = row.get(column)
            if column == "date":
                item[column] = str(value)
            elif column in {"structural_state", "allocation_structural_state"}:
                item[column] = None if pd.isna(value) else str(value)
            else:
                item[column] = None if pd.isna(value) else round(float(value), 6)
        rows.append(item)
    return rows


def _add_equity_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    mapping = {
        "v2_return": "v2_current_equity",
        "v2_baseline_return": "v2_baseline_equity",
        "benchmark_510300_return": "benchmark_510300_equity",
        "benchmark_510500_return": "benchmark_510500_equity",
        "buy_hold_equal_return": "buy_hold_equal_equity",
        "old_s1_actual_return": "old_s1_actual_equity",
        "m2_actual_return": "m2_actual_equity",
    }
    for return_column, equity_column in mapping.items():
        series = pd.to_numeric(result[return_column], errors="coerce")
        result[equity_column] = (1.0 + series.fillna(0.0)).cumprod()
        result.loc[series.isna(), equity_column] = pd.NA
    return result


def _write_history_snapshot_manifest(
    payload: Mapping[str, object],
    *,
    manifest_path: str | Path = SNAPSHOT_MANIFEST_PATH,
    signal_path: str | Path = SIGNAL_SNAPSHOT_PATH,
) -> dict[str, object]:
    generated_at = str(payload["metadata"]["generated_at"])
    manifest = {
        "engine": "V2.6.3 Full Cycle Walk-forward Revalidation Manifest",
        "generated_at": generated_at,
        "storage_policy": "compressed_rebalance_snapshots",
        "full_cycle_backtest_artifact": _display_path(DEFAULT_OUTPUT_PATH),
        "signal_snapshot_artifact": _display_path(signal_path),
        "window": payload["metadata"]["validation_window"],
        "rebalance_signal_count": len(payload.get("signals", {}).get("v2_structural_refined", [])),
        "strict_full_cycle_claim": payload["metadata"]["strict_full_cycle_claim"],
        "soft_macro_gaps": payload["data_quality"]["macro_gap_policy"],
        "constraints": payload["constraints"],
    }
    signals = {
        "engine": "V2.6.3 Compressed Rebalance Signal History",
        "generated_at": generated_at,
        "v2_structural_refined": payload.get("signals", {}).get("v2_structural_refined", []),
        "v2_baseline": payload.get("signals", {}).get("v2_baseline", []),
    }
    for path, item in ((Path(manifest_path), manifest), (Path(signal_path), signals)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def run_full_cycle_backtest(
    *,
    desired_start: str = TARGET_START,
    desired_end: str = TARGET_END,
    rebalance_every_sessions: int = 20,
    cache_only: bool = True,
) -> dict[str, object]:
    start = normalize_trade_date(desired_start)
    end = normalize_trade_date(desired_end)
    coverage = build_data_coverage_audit(desired_start=start, desired_end=end)
    operational = coverage["operational_validation_window"]
    validation_start = max(start, str(operational["start"]))
    validation_end = min(end, str(operational["end"]))
    builder = HistoricalAllocationSnapshotBuilder(
        warmup_start=WARMUP_START,
        macro_start=MACRO_START,
        end_date=validation_end,
        cache_only=cache_only,
    )
    refined = run_v2_allocation_backtest(
        start_date=validation_start,
        end_date=validation_end,
        rebalance_every_sessions=rebalance_every_sessions,
        cache_only=cache_only,
        snapshot_builder=builder,
    )
    legacy = run_v2_allocation_backtest(
        start_date=validation_start,
        end_date=validation_end,
        rebalance_every_sessions=rebalance_every_sessions,
        cache_only=cache_only,
        snapshot_builder=_signal_history_snapshot_builder(list(refined.get("signals") or []), legacy=True),
    )
    frame = _frame_from_payload(refined)
    legacy_frame = _frame_from_payload(legacy, prefix="v2_baseline")
    state_frame = pd.DataFrame(refined.get("equity_curve") or [])
    state_columns = [
        column
        for column in ("date", "structural_state", "allocation_structural_state", "macro_state", "market_structure_state", "theme_risk_level")
        if column in state_frame
    ]
    frame = frame.merge(
        legacy_frame[["date", "v2_baseline_return", "v2_baseline_exposure", "v2_baseline_turnover", "v2_baseline_risk_budget"]],
        on="date",
        how="left",
    )
    frame = frame.merge(state_frame[state_columns], on="date", how="left") if state_columns else frame
    frame["buy_hold_equal_return"] = 0.5 * frame["benchmark_510300_return"] + 0.5 * frame["benchmark_510500_return"]
    frame = _attach_partial_series(frame)
    frame = _add_equity_columns(frame)
    comparison = _comparison_table(frame, refined, legacy)
    phase_attribution = _phase_attribution(frame)
    structural_bull = _structural_bull_contribution(frame)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    soft_gap_blockers = [
        blocker for blocker in coverage.get("blockers", []) if any(indicator in blocker for indicator in SOFT_MACRO_GAPS)
    ]
    hard_blockers = [
        blocker for blocker in coverage.get("blockers", []) if blocker not in soft_gap_blockers
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V2.6.3 Full Cycle Walk-forward Revalidation",
            "generated_at": generated_at,
            "requested_window": {"start": start, "end": end},
            "validation_window": {
                "start": refined["summary"]["start_date"],
                "end": refined["summary"]["end_date"],
                "sessions": refined["summary"]["sessions"],
            },
            "rebalance_every_sessions": rebalance_every_sessions,
            "coverage_status": "walk_forward_completed_with_soft_macro_gaps" if soft_gap_blockers and not hard_blockers else "strict_full_cycle" if not coverage.get("blockers") else "partial_with_hard_gaps",
            "full_cycle_walk_forward_completed": not hard_blockers,
            "strict_full_cycle_claim": not bool(coverage.get("blockers")),
            "signal_timing": "V2 intent is generated after close on date t and applied starting t+1.",
            "walk_forward": True,
            "no_lookahead_bias": True,
            "evaluation_only": True,
        },
        "data_quality": {
            "coverage_audit": coverage,
            "hard_blockers": hard_blockers,
            "soft_blockers": soft_gap_blockers,
            "macro_gap_policy": {
                "missing_indicators": list(SOFT_MACRO_GAPS),
                "confidence_penalty": MACRO_CONFIDENCE_PENALTY,
                "policy": "soft_gap_report_only; not used to tune rules or overwrite historical signals",
                "strict_full_cycle_claim": not bool(coverage.get("blockers")),
            },
        },
        "comparison": comparison,
        "period_attribution": phase_attribution,
        "structural_bull_contribution": structural_bull,
        "equity_curve": _equity_curve_records(frame),
        "signals": {
            "v2_structural_refined": refined.get("signals") or [],
            "v2_baseline": legacy.get("signals") or [],
        },
        "refined_policy": {
            "summary": refined["summary"],
            "performance_metrics": refined["performance_metrics"],
            "validation": refined["validation"],
            "data_quality": refined["data_quality"],
        },
        "v2_baseline": {
            "summary": legacy["summary"],
            "performance_metrics": legacy["performance_metrics"],
            "validation": legacy["validation"],
            "data_quality": legacy["data_quality"],
        },
        "conclusion": [
            "V2.6.3 rebuilds 2015+ rebalance signals from historical data visible at each rebalance date.",
            "No strategy rules, thresholds, allocation maps, factors, labels, or ETF choices were changed.",
            "CN10Y and new_loans remain explicit macro soft gaps, so the result is full-window walk-forward evidence with a strict-cycle caveat.",
        ],
        "constraints": {
            "no_strategy_rule_change": True,
            "no_threshold_tuning": True,
            "no_allocation_change": True,
            "no_new_factor": True,
            "no_manual_state_fix": True,
            "walk_forward": True,
            "no_lookahead_bias": True,
            "no_daily_snapshot_json": True,
            "compressed_rebalance_snapshots_only": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["history_snapshot_manifest"] = _write_history_snapshot_manifest(payload)
    return payload


def write_full_cycle_backtest(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
