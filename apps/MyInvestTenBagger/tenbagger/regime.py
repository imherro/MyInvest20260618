"""Market regime and behavioral state engine for TASK 8."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from tenbagger.config import DEFAULT_DATA_DIR, compact_date, default_start_date, get_setting
from tenbagger.portfolio import load_local_task_data
from tenbagger.universe import UniverseManager


INDEX_CODES = {
    "000300.SH": "CSI300",
    "000905.SH": "CSI500",
}


@dataclass(frozen=True)
class RegimeRunResult:
    daily: pd.DataFrame
    latest: dict[str, Any]
    validation: dict[str, Any]
    history: dict[str, Any]
    data_source: dict[str, Any]


class MarketIndexLoader:
    """Load market index data for behavioral regime modeling."""

    def __init__(
        self,
        token: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        self.token = token or get_setting("TUSHARE_TOKEN")
        self.start_date = compact_date(start_date or default_start_date(days=1400))
        self.end_date = compact_date(end_date)

    def load(
        self,
        data_dir: Path | str = DEFAULT_DATA_DIR,
        refresh: bool = False,
        universe: list[str] | None = None,
        universe_level: str = "dev",
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        data_path = Path(data_dir)
        cache_path = data_path / "regime" / "index_daily.parquet"
        if cache_path.exists() and not refresh:
            frame = pd.read_parquet(cache_path)
            return self._prepare_index_frame(frame), {
                "source": "cached_tushare_index",
                "cache_path": str(cache_path),
                "universe_level": universe_level,
            }

        if self.token:
            try:
                frame = self._load_tushare_index()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(cache_path, index=False)
                return self._prepare_index_frame(frame), {
                    "source": "tushare_index",
                    "cache_path": str(cache_path),
                    "universe_level": universe_level,
                }
            except Exception as exc:  # pragma: no cover - remote API guard
                fallback, meta = self._fallback_equal_weight(data_path, universe=universe)
                meta["tushare_error"] = str(exc)
                meta["universe_level"] = universe_level
                return fallback, meta

        fallback, meta = self._fallback_equal_weight(data_path, universe=universe)
        meta["tushare_error"] = "TUSHARE_TOKEN is not configured"
        meta["universe_level"] = universe_level
        return fallback, meta

    def _load_tushare_index(self) -> pd.DataFrame:
        import tushare as ts

        ts.set_token(self.token)
        pro = ts.pro_api()
        frames = []
        for code, name in INDEX_CODES.items():
            frame = pro.index_daily(
                ts_code=code,
                start_date=self.start_date,
                end_date=self.end_date,
                fields="ts_code,trade_date,close,vol,amount",
            )
            if frame.empty:
                continue
            frame = frame.rename(
                columns={
                    "trade_date": "date",
                    "vol": "volume",
                    "amount": "amount",
                }
            )
            frame["index_name"] = name
            frames.append(frame)
        if not frames:
            raise RuntimeError("TuShare returned no index rows for CSI300 or CSI500.")
        return pd.concat(frames, ignore_index=True)

    def _fallback_equal_weight(self, data_path: Path, universe: list[str] | None) -> tuple[pd.DataFrame, dict[str, Any]]:
        _factors, prices = load_local_task_data(data_path, universe=universe)
        frame = prices[["ts_code", "date", "close"]].copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["date", "ts_code", "close"]).sort_values(["ts_code", "date"])
        frame["ret"] = frame.groupby("ts_code")["close"].pct_change()
        market = frame.groupby("date", as_index=False).agg(market_return=("ret", "mean"))
        market["close"] = (1 + market["market_return"].fillna(0.0)).cumprod() * 1000
        market["ts_code"] = "EQUAL_WEIGHT"
        market["index_name"] = "EQUAL_WEIGHT_UNIVERSE"
        market["volume"] = 0.0
        market["amount"] = 0.0
        market["date"] = market["date"].dt.strftime("%Y-%m-%d")
        return self._prepare_index_frame(market), {"source": "equal_weight_universe"}

    @staticmethod
    def _prepare_index_frame(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        if result["date"].dt.strftime("%Y%m%d").eq(result["date"].astype(str)).any():
            result["date"] = pd.to_datetime(result["date"].astype(str), format="%Y%m%d", errors="coerce")
        result["close"] = pd.to_numeric(result["close"], errors="coerce")
        result["volume"] = pd.to_numeric(result.get("volume", 0.0), errors="coerce").fillna(0.0)
        result["amount"] = pd.to_numeric(result.get("amount", 0.0), errors="coerce").fillna(0.0)
        if "index_name" not in result:
            result["index_name"] = result["ts_code"].map(INDEX_CODES).fillna(result["ts_code"])
        return result.dropna(subset=["date", "ts_code", "close"]).sort_values(["ts_code", "date"])


class MarketRegimeEngine:
    """Convert index prices, volatility, and liquidity into behavioral states."""

    def run(self, index_data: pd.DataFrame, data_source: dict[str, Any] | None = None) -> RegimeRunResult:
        daily = self._market_frame(index_data)
        daily = self._attach_trend(daily)
        daily = self._attach_volatility(daily)
        daily = self._attach_liquidity(daily)
        daily = self._attach_behavior(daily)
        daily = self._attach_transition(daily)
        daily = daily.dropna(subset=["date"]).reset_index(drop=True)
        validation = RegimeValidator().validate(daily)
        history = self._history(daily)
        latest = _clean_record(daily.tail(1).iloc[0].to_dict()) if not daily.empty else {}
        return RegimeRunResult(
            daily=daily,
            latest=latest,
            validation=validation,
            history=history,
            data_source=data_source or {},
        )

    @staticmethod
    def _market_frame(index_data: pd.DataFrame) -> pd.DataFrame:
        frame = index_data.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values(["ts_code", "date"])
        frame["index_return"] = frame.groupby("ts_code")["close"].pct_change()
        market = frame.groupby("date", as_index=False).agg(
            market_return=("index_return", "mean"),
            amount=("amount", "sum"),
            volume=("volume", "sum"),
            index_count=("ts_code", "nunique"),
        )
        market["market_return"] = market["market_return"].fillna(0.0)
        market["market_nav"] = (1 + market["market_return"]).cumprod()
        market["date"] = pd.to_datetime(market["date"], errors="coerce")
        return market.sort_values("date")

    def _attach_trend(self, daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["return_20d"] = result["market_nav"].pct_change(20)
        result["return_60d"] = result["market_nav"].pct_change(60)
        result["return_120d"] = result["market_nav"].pct_change(120)
        for window in [20, 60, 120]:
            ma = result["market_nav"].rolling(window, min_periods=max(5, window // 3)).mean()
            result[f"ma_{window}_slope"] = ma.pct_change(20).fillna(0.0)
        result["trend_persistence"] = (
            (result["market_return"] > 0).rolling(20, min_periods=5).mean().fillna(0.5)
        )
        raw_strength = (
            result["return_60d"].abs().fillna(0.0) * 3.0
            + result["ma_20_slope"].abs().fillna(0.0) * 6.0
            + (result["trend_persistence"] - 0.5).abs().fillna(0.0)
        )
        result["trend_strength"] = raw_strength.clip(0, 1)
        result["trend_regime"] = "sideways"
        bull = (
            ((result["return_60d"] > 0.05) & (result["ma_20_slope"] > 0))
            | ((result["return_120d"] > 0.08) & (result["trend_persistence"] >= 0.55))
        )
        bear = (
            ((result["return_60d"] < -0.05) & (result["ma_20_slope"] < 0))
            | ((result["return_120d"] < -0.10) & (result["trend_persistence"] <= 0.45))
        )
        result.loc[bull, "trend_regime"] = "bull"
        result.loc[bear, "trend_regime"] = "bear"
        return result

    @staticmethod
    def _attach_volatility(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["realized_vol_20d"] = result["market_return"].rolling(20, min_periods=10).std() * (252**0.5)
        result["realized_vol_60d"] = result["market_return"].rolling(60, min_periods=20).std() * (252**0.5)
        result["volatility_percentile"] = _rolling_percentile(result["realized_vol_20d"], window=756, min_periods=60)
        result["volatility_regime"] = "medium"
        result.loc[result["volatility_percentile"] <= 0.33, "volatility_regime"] = "low"
        result.loc[result["volatility_percentile"] >= 0.67, "volatility_regime"] = "high"
        result["volatility_score"] = result["volatility_percentile"].fillna(0.5).clip(0, 1)
        return result

    @staticmethod
    def _attach_liquidity(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        basis = result["amount"].where(result["amount"] > 0, result["volume"])
        result["liquidity_value"] = basis.fillna(0.0)
        result["liquidity_ma20"] = result["liquidity_value"].rolling(20, min_periods=5).mean()
        result["liquidity_ma60"] = result["liquidity_value"].rolling(60, min_periods=20).mean()
        result["liquidity_ratio"] = (
            result["liquidity_ma20"] / result["liquidity_ma60"].replace({0: pd.NA})
        ).fillna(1.0)
        result["liquidity_percentile"] = _rolling_percentile(result["liquidity_value"], window=756, min_periods=60)
        result["liquidity_regime"] = "neutral"
        expansion = (result["liquidity_ratio"] > 1.15) & (result["liquidity_percentile"].fillna(0.5) >= 0.55)
        contraction = (result["liquidity_ratio"] < 0.85) & (result["liquidity_percentile"].fillna(0.5) <= 0.45)
        result.loc[expansion, "liquidity_regime"] = "expansion"
        result.loc[contraction, "liquidity_regime"] = "contraction"
        result["liquidity_score"] = result["liquidity_percentile"].fillna(0.5).clip(0, 1)
        return result

    @staticmethod
    def _attach_behavior(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        result["behavior_state"] = "transition"
        panic = (
            (result["trend_regime"] == "bear")
            & (result["volatility_regime"] == "high")
            & (result["liquidity_regime"] != "expansion")
        )
        euphoria = (
            (result["trend_regime"] == "bull")
            & (result["liquidity_regime"] == "expansion")
            & (result["volatility_regime"] != "high")
        )
        risk_on = (
            (result["trend_regime"].isin(["bull", "sideways"]))
            & (result["liquidity_regime"].isin(["expansion", "neutral"]))
            & (result["volatility_regime"] != "high")
        )
        risk_off = (
            (result["trend_regime"] == "bear")
            | ((result["volatility_regime"] == "high") & (result["liquidity_regime"] != "expansion"))
        )
        result.loc[risk_on, "behavior_state"] = "risk_on"
        result.loc[risk_off, "behavior_state"] = "risk_off"
        result.loc[euphoria, "behavior_state"] = "euphoria"
        result.loc[panic, "behavior_state"] = "panic"
        return result

    @staticmethod
    def _attach_transition(daily: pd.DataFrame) -> pd.DataFrame:
        result = daily.copy()
        state_columns = ["trend_regime", "volatility_regime", "liquidity_regime", "behavior_state"]
        changes = pd.Series(0.0, index=result.index)
        for column in state_columns:
            changed = result[column].ne(result[column].shift(1)).astype(float)
            changed.iloc[0] = 0.0
            changes = changes + changed
        result["daily_regime_changes"] = changes
        result["recent_change_rate"] = (changes > 0).rolling(20, min_periods=5).mean().fillna(0.0)
        vol_pressure = (result["volatility_score"].fillna(0.5) - 0.5).clip(lower=0.0) * 0.4
        result["regime_change_probability"] = (
            result["recent_change_rate"] * 0.7 + (changes / len(state_columns)) * 0.3 + vol_pressure
        ).clip(0, 1)
        result["stability_score"] = (1 - result["recent_change_rate"]).clip(0, 1)
        return result

    @staticmethod
    def _history(daily: pd.DataFrame) -> dict[str, Any]:
        tail = daily.tail(120).copy()
        for column in ["date"]:
            tail[column] = tail[column].dt.strftime("%Y-%m-%d")
        distribution = {
            column: daily[column].value_counts(normalize=True).round(4).to_dict()
            for column in ["trend_regime", "volatility_regime", "liquidity_regime", "behavior_state"]
        }
        recent_30 = daily.tail(30).copy()
        recent_30["date"] = recent_30["date"].dt.strftime("%Y-%m-%d")
        change_rows = recent_30[recent_30["daily_regime_changes"] > 0]
        return {
            "distribution": distribution,
            "recent_30": _records(recent_30),
            "recent_30_changes": _records(change_rows),
            "chart_tail": _records(tail),
        }


class RegimeValidator:
    """Validate continuity and non-random behavior of regime labels."""

    def validate(self, daily: pd.DataFrame) -> dict[str, Any]:
        if daily.empty:
            return {}
        behavior = daily["behavior_state"].astype(str)
        same_as_previous = behavior.eq(behavior.shift(1))
        same_as_previous.iloc[0] = True
        durations = self._duration_distribution(behavior)
        transition_frequency = float((~same_as_previous).sum() / max(len(behavior) - 1, 1))
        recent_transition_frequency = float(
            (daily.tail(30)["daily_regime_changes"] > 0).mean()
        )
        return {
            "uses_future_return_labels": False,
            "walk_forward_features_only": True,
            "regime_autocorrelation": float(same_as_previous.mean()),
            "transition_frequency": transition_frequency,
            "recent_30d_transition_frequency": recent_transition_frequency,
            "mean_duration_days": float(durations["duration"].mean()) if not durations.empty else 0.0,
            "median_duration_days": float(durations["duration"].median()) if not durations.empty else 0.0,
            "max_duration_days": int(durations["duration"].max()) if not durations.empty else 0,
            "duration_distribution": durations.to_dict(orient="records"),
            "transition_not_overfit": bool(transition_frequency <= 0.35),
            "regime_has_continuity": bool(same_as_previous.mean() >= 0.55),
        }

    @staticmethod
    def _duration_distribution(series: pd.Series) -> pd.DataFrame:
        rows = []
        current_state = None
        start_idx = 0
        for idx, value in enumerate(series.tolist()):
            if current_state is None:
                current_state = value
                start_idx = idx
                continue
            if value != current_state:
                rows.append({"behavior_state": current_state, "duration": idx - start_idx})
                current_state = value
                start_idx = idx
        if current_state is not None:
            rows.append({"behavior_state": current_state, "duration": len(series) - start_idx})
        return pd.DataFrame(rows)


def run_market_regime_pipeline(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    refresh_index: bool = False,
    universe_level: str = "dev",
) -> RegimeRunResult:
    universe = UniverseManager().resolve(universe_level)
    loader = MarketIndexLoader()
    index_data, source = loader.load(
        data_dir=data_dir,
        refresh=refresh_index,
        universe=universe.codes,
        universe_level=universe.level,
    )
    source["universe"] = universe.to_api()
    return MarketRegimeEngine().run(index_data, data_source=source)


def _rolling_percentile(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")

    def percentile(window_values: pd.Series) -> float:
        current = window_values.iloc[-1]
        valid = window_values.dropna()
        if pd.isna(current) or len(valid) < 2:
            return 0.5
        return float((valid <= current).mean())

    return values.rolling(window, min_periods=min_periods).apply(percentile, raw=False).fillna(0.5)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = []
    for row in frame.to_dict(orient="records"):
        clean.append(_clean_record(row))
    return clean


def _clean_record(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, pd.Timestamp):
            result[key] = value.strftime("%Y-%m-%d")
        elif pd.isna(value):
            result[key] = None
        elif hasattr(value, "item"):
            result[key] = value.item()
        else:
            result[key] = value
    return result
