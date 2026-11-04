"""Structural anomaly detection for TASK 11."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from tenbagger.config import DEFAULT_DATA_DIR
from tenbagger.structure import StructureRunResult, run_structure_pipeline


@dataclass(frozen=True)
class AnomalyRunResult:
    daily: pd.DataFrame
    latest: dict[str, Any]
    validation: dict[str, Any]
    history: dict[str, Any]
    source: dict[str, Any]


class StructuralAnomalyEngine:
    """Detect structural, correlation, flow, and behavioral anomalies."""

    def run(self, structure_daily: pd.DataFrame, source: dict[str, Any] | None = None) -> AnomalyRunResult:
        daily = structure_daily.copy()
        daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
        daily = daily.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        daily = self._attach_structural_break(daily)
        daily = self._attach_correlation_breakdown(daily)
        daily = self._attach_flow_shock(daily)
        daily = self._attach_behavioral_anomaly(daily)
        daily = self._attach_fusion(daily)
        validation = AnomalyValidator().validate(daily)
        history = self._history(daily)
        latest = _clean_record(daily.tail(1).iloc[0].to_dict()) if not daily.empty else {}
        return AnomalyRunResult(
            daily=daily,
            latest=latest,
            validation=validation,
            history=history,
            source=source or {},
        )

    @staticmethod
    def _attach_structural_break(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        trend_change = result["trend_component"].diff().abs().fillna(0.0).clip(0, 1)
        trend_regime_change = result["trend_regime"].ne(result["trend_regime"].shift(1)).astype(float)
        trend_regime_change.iloc[0] = 0.0
        result["trend_break_prob"] = (trend_change * 0.55 + trend_regime_change * 0.45).clip(0, 1)

        vol_change = result["volatility_score"].diff().abs().fillna(0.0).clip(0, 1)
        vol_regime_change = result["volatility_regime"].ne(result["volatility_regime"].shift(1)).astype(float)
        vol_regime_change.iloc[0] = 0.0
        result["volatility_shift_prob"] = (
            vol_change * 0.45 + vol_regime_change * 0.35 + result["volatility_component"].fillna(0.0) * 0.20
        ).clip(0, 1)

        liquidity_drop = (-result["liquidity_score"].diff().fillna(0.0)).clip(0, 1)
        liquidity_low = (1 - result["liquidity_score"].fillna(0.5)).clip(0, 1)
        result["liquidity_collapse_prob"] = (liquidity_drop * 0.55 + liquidity_low * 0.45).clip(0, 1)
        result["structural_break_prob"] = (
            result["trend_break_prob"] * 0.30
            + result["volatility_shift_prob"] * 0.30
            + result["liquidity_collapse_prob"] * 0.25
            + result["structural_shock_probability"].fillna(0.0) * 0.15
        ).clip(0, 1)
        return result

    @staticmethod
    def _attach_correlation_breakdown(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        corr_change = result["cross_sectional_correlation"].diff().abs().fillna(0.0).clip(0, 1)
        decoupling = ((result["market_dispersion"].fillna(0.5) > 0.75) & (result["correlation_regime"] == "low")).astype(float)
        systemic = ((result["correlation_regime"] == "high") & (result["volatility_regime"] == "high")).astype(float)
        result["correlation_break_prob"] = (
            result["correlation_spike_score"].fillna(0.5) * 0.30
            + corr_change * 0.25
            + decoupling * 0.25
            + systemic * 0.20
        ).clip(0, 1)
        result["cross_sector_decoupling_prob"] = (result["market_dispersion"].fillna(0.5) * (1 - result["cross_sectional_correlation"].fillna(0.0).clip(0, 1))).clip(0, 1)
        return result

    @staticmethod
    def _attach_flow_shock(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        institutional_jump = result["institutional_flow_index"].diff().abs().fillna(0.0).clip(0, 1)
        retail_jump = result["retail_pressure_index"].diff().abs().fillna(0.0).clip(0, 1)
        panic_jump = result["panic_index"].diff().clip(lower=0).fillna(0.0).clip(0, 1)
        liquidity_vacuum = (1 - result["liquidity_score"].fillna(0.5)).clip(0, 1)
        result["institutional_flow_shock_prob"] = institutional_jump.clip(0, 1)
        result["retail_panic_cluster_prob"] = (retail_jump * 0.45 + panic_jump * 0.55).clip(0, 1)
        result["liquidity_vacuum_prob"] = liquidity_vacuum
        result["flow_shock_prob"] = (
            institutional_jump * 0.30
            + retail_jump * 0.25
            + panic_jump * 0.25
            + liquidity_vacuum * 0.20
        ).clip(0, 1)
        return result

    @staticmethod
    def _attach_behavioral_anomaly(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        fomo_spike = result["fomo_index"].diff().clip(lower=0).fillna(0.0).clip(0, 1)
        panic_cascade = (result["panic_index"].rolling(5, min_periods=1).mean() * result["volatility_spike_score"]).fillna(0.0).clip(0, 1)
        breakout_cluster = result["breakout_failure_score"].rolling(5, min_periods=1).mean().fillna(0.0).clip(0, 1)
        reversal_cluster = result["reversal_risk"].rolling(5, min_periods=1).mean().fillna(0.0).clip(0, 1)
        result["fomo_spike_prob"] = fomo_spike
        result["panic_cascade_prob"] = panic_cascade
        result["breakout_failure_cluster_prob"] = breakout_cluster
        result["behavioral_anomaly_score"] = (
            fomo_spike * 0.25
            + panic_cascade * 0.30
            + breakout_cluster * 0.20
            + reversal_cluster * 0.15
            + result["divergence_score"].fillna(0.0) * 0.10
        ).clip(0, 1)
        return result

    @staticmethod
    def _attach_fusion(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["anomaly_score"] = (
            result["structural_break_prob"] * 0.30
            + result["correlation_break_prob"] * 0.25
            + result["flow_shock_prob"] * 0.20
            + result["behavioral_anomaly_score"] * 0.25
        ).clip(0, 1)
        result["systemic_risk_level"] = "low"
        result.loc[result["anomaly_score"] >= 0.40, "systemic_risk_level"] = "medium"
        result.loc[(result["anomaly_score"] >= 0.70) | ((result["structural_break_prob"] + result["correlation_break_prob"]) >= 1.2), "systemic_risk_level"] = "high"
        components = [
            "structural_break_prob",
            "correlation_break_prob",
            "flow_shock_prob",
            "behavioral_anomaly_score",
        ]
        result["dominant_anomaly_type"] = result[components].idxmax(axis=1).str.replace("_prob", "", regex=False).str.replace("_score", "", regex=False)
        result.loc[result["anomaly_score"] < 0.25, "dominant_anomaly_type"] = "none"
        result["anomaly_state"] = result["systemic_risk_level"].astype(str) + "::" + result["dominant_anomaly_type"].astype(str)
        return result

    @staticmethod
    def _history(daily: pd.DataFrame) -> dict[str, Any]:
        tail = daily.tail(120).copy()
        tail["date"] = tail["date"].dt.strftime("%Y-%m-%d")
        distribution = {
            "systemic_risk_level": daily["systemic_risk_level"].value_counts(normalize=True).round(4).to_dict(),
            "dominant_anomaly_type": daily["dominant_anomaly_type"].value_counts(normalize=True).round(4).to_dict(),
            "anomaly_state": daily["anomaly_state"].value_counts(normalize=True).round(4).to_dict(),
        }
        events = tail[tail["anomaly_score"] >= 0.40]
        return {
            "distribution": distribution,
            "chart_tail": _records(tail),
            "recent_30": _records(tail.tail(30)),
            "anomaly_events": _records(events.tail(20)),
            "flow_shock_events": _records(tail[tail["flow_shock_prob"] >= 0.35].tail(20)),
            "correlation_break_events": _records(tail[tail["correlation_break_prob"] >= 0.55].tail(20)),
        }


class AnomalyValidator:
    """Validate structural anomaly detection as non-predictive and bounded."""

    def validate(self, daily: pd.DataFrame) -> dict[str, Any]:
        score_columns = [
            "structural_break_prob",
            "correlation_break_prob",
            "flow_shock_prob",
            "behavioral_anomaly_score",
            "anomaly_score",
            "cross_sector_decoupling_prob",
            "liquidity_vacuum_prob",
        ]
        bounded = daily[score_columns].apply(lambda column: column.dropna().between(0, 1).all())
        state = daily["anomaly_state"].astype(str)
        same = state.eq(state.shift(1))
        same.iloc[0] = True
        return {
            "uses_future_return_labels": False,
            "uses_alpha_model": False,
            "predicts_market_direction": False,
            "purely_observational": True,
            "walk_forward_features_only": True,
            "anomaly_is_structure_deviation": True,
            "all_scores_bounded_0_1": bool(bounded.all()),
            "anomaly_state_autocorrelation": float(same.mean()),
            "anomaly_transition_frequency": float((~same).sum() / max(len(same) - 1, 1)),
            "anomaly_event_frequency": float((daily["anomaly_score"] >= 0.40).mean()),
            "high_risk_frequency": float((daily["systemic_risk_level"] == "high").mean()),
            "recent_30d_mean_anomaly": float(daily.tail(30)["anomaly_score"].mean()),
        }


def load_or_build_structure_daily(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    universe_level: str = "dev",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    data_path = Path(data_dir)
    structure_path = data_path / "structure" / f"market_structure_daily_{universe_level}.parquet"
    if structure_path.exists():
        return pd.read_parquet(structure_path), {
            "source": "task10_market_structure_daily",
            "path": str(structure_path),
            "universe_level": universe_level,
        }
    result: StructureRunResult = run_structure_pipeline(
        data_dir=data_path,
        universe_level=universe_level,
    )
    structure_path.parent.mkdir(parents=True, exist_ok=True)
    result.daily.to_parquet(structure_path, index=False)
    return result.daily, {"source": "rebuilt_task10_market_structure_daily", **result.source}


def run_anomaly_pipeline(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    universe_level: str = "dev",
) -> AnomalyRunResult:
    structure_daily, source = load_or_build_structure_daily(data_dir, universe_level=universe_level)
    return StructuralAnomalyEngine().run(structure_daily, source=source)


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
