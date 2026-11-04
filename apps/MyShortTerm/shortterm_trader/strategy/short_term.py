from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from shortterm_trader.strategy.indicators import atr, rsi, sma
from shortterm_trader.strategy.risk import RiskParams, attach_risk_columns


@dataclass(frozen=True)
class StrategyParams:
    min_history: int = 60
    breakout_window: int = 20
    min_score: int = 70
    max_atr_pct: float = 0.09
    volume_surge: float = 1.35
    risk: RiskParams = RiskParams()


def build_signal_frame(bars: pd.DataFrame, params: StrategyParams | None = None) -> pd.DataFrame:
    cfg = params or StrategyParams()
    frame = bars.sort_values("date").reset_index(drop=True).copy()
    if len(frame) < cfg.min_history:
        raise ValueError(f"need at least {cfg.min_history} bars, got {len(frame)}")

    frame["ma5"] = sma(frame["close"], 5)
    frame["ma10"] = sma(frame["close"], 10)
    frame["ma20"] = sma(frame["close"], 20)
    frame["ma60"] = sma(frame["close"], 60)
    frame["rsi14"] = rsi(frame["close"], 14)
    frame["atr14"] = atr(frame, 14)
    frame["atr_pct"] = frame["atr14"] / frame["close"]
    frame["vol_ma20"] = sma(frame["volume"], 20)
    frame["high_n_prev"] = frame["high"].rolling(cfg.breakout_window, min_periods=cfg.breakout_window).max().shift(1)
    frame["low_n_prev"] = frame["low"].rolling(cfg.breakout_window, min_periods=cfg.breakout_window).min().shift(1)
    frame["ret_5d"] = frame["close"] / frame["close"].shift(5) - 1
    frame["ret_20d"] = frame["close"] / frame["close"].shift(20) - 1

    frame["trend_ok"] = (frame["ma5"] > frame["ma10"]) & (frame["ma10"] > frame["ma20"]) & (frame["close"] > frame["ma60"])
    frame["breakout_ok"] = frame["close"] > frame["high_n_prev"]
    frame["volume_ok"] = frame["volume"] > frame["vol_ma20"] * cfg.volume_surge
    frame["momentum_ok"] = (frame["ret_5d"] > 0.02) & (frame["ret_20d"] > 0)
    frame["rsi_ok"] = frame["rsi14"].between(45, 75, inclusive="both")
    frame["volatility_ok"] = frame["atr_pct"].between(0.005, cfg.max_atr_pct, inclusive="both")

    score_columns = {
        "trend_ok": 25,
        "breakout_ok": 20,
        "volume_ok": 15,
        "momentum_ok": 15,
        "rsi_ok": 15,
        "volatility_ok": 10,
    }
    frame["score"] = 0
    for column, weight in score_columns.items():
        frame["score"] += frame[column].fillna(False).astype(int) * weight
    frame["signal"] = frame["score"] >= cfg.min_score
    frame = attach_risk_columns(frame, cfg.risk)
    frame["setup"] = frame.apply(_setup_label, axis=1)
    return frame


def latest_signal(bars: pd.DataFrame, params: StrategyParams | None = None) -> dict[str, object]:
    frame = build_signal_frame(bars, params=params)
    row = frame.iloc[-1]
    keys = [
        "symbol",
        "date",
        "close",
        "score",
        "signal",
        "setup",
        "stop_price",
        "take_profit_price",
        "stop_loss_pct",
        "take_profit_pct",
        "position_weight_cap",
        "source",
    ]
    result: dict[str, object] = {}
    for key in keys:
        if key in row:
            value = row[key]
            if hasattr(value, "item"):
                value = value.item()
            result[key] = value
    return result


def _setup_label(row: pd.Series) -> str:
    tags: list[str] = []
    if bool(row.get("trend_ok", False)):
        tags.append("trend")
    if bool(row.get("breakout_ok", False)):
        tags.append("breakout")
    if bool(row.get("volume_ok", False)):
        tags.append("volume")
    if bool(row.get("momentum_ok", False)):
        tags.append("momentum")
    if bool(row.get("volatility_ok", False)):
        tags.append("risk-ok")
    return "+".join(tags) if tags else "none"

