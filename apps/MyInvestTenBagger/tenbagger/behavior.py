"""Behavioral flow engine for TASK 9."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from tenbagger.config import DEFAULT_DATA_DIR
from tenbagger.regime import RegimeRunResult, run_market_regime_pipeline


@dataclass(frozen=True)
class BehaviorRunResult:
    daily: pd.DataFrame
    latest: dict[str, Any]
    validation: dict[str, Any]
    history: dict[str, Any]
    source: dict[str, Any]


class BehaviorFlowEngine:
    """Infer market actors and behavioral pressure from observable market behavior."""

    def run(self, regime_daily: pd.DataFrame, source: dict[str, Any] | None = None) -> BehaviorRunResult:
        daily = regime_daily.copy()
        daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
        daily = daily.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        daily = self._attach_behavior_features(daily)
        daily = self._attach_actor_pressure(daily)
        daily = self._attach_panic_fomo(daily)
        daily = self._attach_crowding(daily)
        daily = self._attach_flow_price_divergence(daily)
        daily = self._attach_overlay(daily)
        validation = BehaviorValidator().validate(daily)
        history = self._history(daily)
        latest = _clean_record(daily.tail(1).iloc[0].to_dict()) if not daily.empty else {}
        return BehaviorRunResult(
            daily=daily,
            latest=latest,
            validation=validation,
            history=history,
            source=source or {},
        )

    @staticmethod
    def _attach_behavior_features(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["return_5d"] = result["market_nav"].pct_change(5)
        result["return_10d"] = result["market_nav"].pct_change(10)
        result["momentum_acceleration"] = (
            result["return_20d"].fillna(0.0) - result["return_60d"].fillna(0.0)
        ).clip(-0.2, 0.2)
        result["volume_surge_score"] = ((result["liquidity_ratio"].fillna(1.0) - 1.0) / 0.35).clip(0, 1)
        result["volatility_spike_score"] = ((result["volatility_percentile"].fillna(0.5) - 0.55) / 0.45).clip(0, 1)
        prior_strength = result["return_10d"].shift(1).fillna(0.0).clip(lower=0.0)
        negative_reversal = (-result["market_return"].fillna(0.0) / 0.03).clip(0, 1)
        result["breakout_failure_score"] = (
            (prior_strength / 0.06).clip(0, 1) * negative_reversal * (0.5 + result["volume_surge_score"] * 0.5)
        ).clip(0, 1)
        result["reversal_pressure_score"] = (
            negative_reversal * (0.4 + result["volatility_spike_score"] * 0.4 + result["volume_surge_score"] * 0.2)
        ).clip(0, 1)
        return result

    @staticmethod
    def _attach_actor_pressure(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["retail_pressure_index"] = (
            result["volatility_spike_score"] * 0.35
            + result["breakout_failure_score"] * 0.30
            + result["volume_surge_score"] * 0.20
            + result["reversal_pressure_score"] * 0.15
        ).clip(0, 1)
        calm_trend_score = (
            result["trend_persistence"].fillna(0.5) * 0.35
            + result["trend_strength"].fillna(0.0) * 0.25
            + (1 - result["volatility_spike_score"]) * 0.20
            + result["liquidity_score"].fillna(0.5) * 0.20
        )
        result["institutional_flow_index"] = calm_trend_score.clip(0, 1)
        result["dominant_actor"] = "balanced"
        result.loc[result["retail_pressure_index"] > result["institutional_flow_index"] + 0.12, "dominant_actor"] = "retail"
        result.loc[result["institutional_flow_index"] > result["retail_pressure_index"] + 0.12, "dominant_actor"] = "institutional"
        return result

    @staticmethod
    def _attach_panic_fomo(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        positive_momentum = (result["momentum_acceleration"] / 0.08).clip(0, 1)
        positive_price = (result["return_5d"].fillna(0.0) / 0.04).clip(0, 1)
        result["fomo_index"] = (
            positive_momentum * 0.35
            + result["volume_surge_score"] * 0.25
            + positive_price * 0.25
            + (result["trend_regime"].eq("bull").astype(float) * 0.15)
        ).clip(0, 1)
        negative_price = (-result["return_5d"].fillna(0.0) / 0.05).clip(0, 1)
        result["panic_index"] = (
            result["volatility_spike_score"] * 0.35
            + negative_price * 0.30
            + result["reversal_pressure_score"] * 0.20
            + (result["behavior_state"].eq("panic").astype(float) * 0.15)
        ).clip(0, 1)
        return result

    @staticmethod
    def _attach_crowding(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["positioning_crowdedness"] = (
            result[["fomo_index", "panic_index", "retail_pressure_index"]].max(axis=1) * 0.55
            + result["liquidity_score"].fillna(0.5) * 0.25
            + result["trend_strength"].fillna(0.0) * 0.20
        ).clip(0, 1)
        result["reversal_risk"] = (
            result["positioning_crowdedness"] * 0.45
            + result["volatility_spike_score"] * 0.30
            + result["breakout_failure_score"] * 0.25
        ).clip(0, 1)
        result["crowding_level"] = pd.cut(
            result["positioning_crowdedness"],
            bins=[-0.01, 0.35, 0.6, 0.8, 1.01],
            labels=["low", "medium", "high", "extreme"],
        ).astype(str)
        return result

    @staticmethod
    def _attach_flow_price_divergence(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        flow_expanding = result["liquidity_score"].fillna(0.5) >= 0.7
        flow_contracting = result["liquidity_score"].fillna(0.5) <= 0.35
        price_up = result["return_5d"].fillna(0.0) > 0.015
        price_down = result["return_5d"].fillna(0.0) < -0.015
        result["flow_price_divergence"] = "neutral"
        result.loc[flow_expanding & ~price_up, "flow_price_divergence"] = "buying_without_price_response"
        result.loc[price_up & flow_contracting, "flow_price_divergence"] = "price_up_flow_down"
        result.loc[flow_expanding & price_up, "flow_price_divergence"] = "aligned_accumulation"
        result.loc[flow_contracting & price_down, "flow_price_divergence"] = "aligned_distribution"
        result["divergence_score"] = 0.0
        result.loc[result["flow_price_divergence"].isin(["buying_without_price_response", "price_up_flow_down"]), "divergence_score"] = (
            result["liquidity_score"].fillna(0.5).sub(0.5).abs() * 0.6
            + result["return_5d"].fillna(0.0).abs().clip(0, 0.08) / 0.08 * 0.4
        ).clip(0, 1)
        return result

    @staticmethod
    def _attach_overlay(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["behavior_overlay_state"] = "neutral_behavior"
        result.loc[(result["panic_index"] >= 0.65) & (result["dominant_actor"] == "retail"), "behavior_overlay_state"] = "retail_panic"
        result.loc[(result["fomo_index"] >= 0.65) & (result["dominant_actor"] == "retail"), "behavior_overlay_state"] = "retail_fomo"
        result.loc[(result["institutional_flow_index"] >= 0.65) & (result["flow_price_divergence"] == "aligned_accumulation"), "behavior_overlay_state"] = "institutional_accumulation"
        result.loc[(result["flow_price_divergence"] == "buying_without_price_response"), "behavior_overlay_state"] = "absorption_or_distribution"
        result.loc[(result["crowding_level"].isin(["high", "extreme"])) & (result["reversal_risk"] >= 0.65), "behavior_overlay_state"] = "crowded_reversal_risk"
        result["joint_regime_behavior"] = result["behavior_state"].astype(str) + "::" + result["behavior_overlay_state"].astype(str)
        return result

    @staticmethod
    def _history(daily: pd.DataFrame) -> dict[str, Any]:
        tail = daily.tail(120).copy()
        tail["date"] = tail["date"].dt.strftime("%Y-%m-%d")
        distribution = {
            "dominant_actor": daily["dominant_actor"].value_counts(normalize=True).round(4).to_dict(),
            "crowding_level": daily["crowding_level"].value_counts(normalize=True).round(4).to_dict(),
            "flow_price_divergence": daily["flow_price_divergence"].value_counts(normalize=True).round(4).to_dict(),
            "behavior_overlay_state": daily["behavior_overlay_state"].value_counts(normalize=True).round(4).to_dict(),
        }
        return {
            "distribution": distribution,
            "chart_tail": _records(tail),
            "recent_30": _records(tail.tail(30)),
            "divergence_events": _records(tail[tail["divergence_score"] > 0].tail(20)),
        }


class BehaviorValidator:
    """Validate TASK 9 as a descriptive, walk-forward behavior model."""

    def validate(self, daily: pd.DataFrame) -> dict[str, Any]:
        if daily.empty:
            return {}
        overlay = daily["behavior_overlay_state"].astype(str)
        same = overlay.eq(overlay.shift(1))
        same.iloc[0] = True
        numeric_columns = [
            "retail_pressure_index",
            "institutional_flow_index",
            "panic_index",
            "fomo_index",
            "positioning_crowdedness",
            "reversal_risk",
            "divergence_score",
        ]
        range_checks = {
            column: bool(daily[column].between(0, 1).all())
            for column in numeric_columns
        }
        retail_inst_corr = daily["retail_pressure_index"].corr(daily["institutional_flow_index"])
        return {
            "uses_future_return_labels": False,
            "walk_forward_features_only": True,
            "uses_factor_alpha": False,
            "all_scores_bounded_0_1": bool(all(range_checks.values())),
            "score_range_checks": range_checks,
            "overlay_autocorrelation": float(same.mean()),
            "behavior_transition_frequency": float((~same).sum() / max(len(same) - 1, 1)),
            "divergence_event_frequency": float((daily["divergence_score"] > 0).mean()),
            "retail_institutional_correlation": 0.0 if pd.isna(retail_inst_corr) else float(retail_inst_corr),
            "recent_30d_mean_panic": float(daily.tail(30)["panic_index"].mean()),
            "recent_30d_mean_fomo": float(daily.tail(30)["fomo_index"].mean()),
        }


def load_or_build_regime_daily(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    universe_level: str = "dev",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    data_path = Path(data_dir)
    regime_path = data_path / "regime" / f"market_regime_daily_{universe_level}.parquet"
    if regime_path.exists():
        return pd.read_parquet(regime_path), {
            "source": "task8_market_regime_daily",
            "path": str(regime_path),
            "universe_level": universe_level,
        }
    result: RegimeRunResult = run_market_regime_pipeline(
        data_dir=data_path,
        universe_level=universe_level,
    )
    regime_path.parent.mkdir(parents=True, exist_ok=True)
    result.daily.to_parquet(regime_path, index=False)
    return result.daily, {"source": "rebuilt_task8_market_regime_daily", **result.data_source}


def run_behavior_pipeline(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    universe_level: str = "dev",
) -> BehaviorRunResult:
    regime_daily, source = load_or_build_regime_daily(data_dir, universe_level=universe_level)
    return BehaviorFlowEngine().run(regime_daily, source=source)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_clean_record(row) for row in frame.to_dict(orient="records")]


def _clean_record(row: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, pd.Timestamp):
            clean[key] = value.strftime("%Y-%m-%d")
        elif pd.isna(value):
            clean[key] = None
        elif hasattr(value, "item"):
            clean[key] = value.item()
        else:
            clean[key] = value
    return clean
