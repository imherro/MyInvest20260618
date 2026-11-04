from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RiskParams:
    atr_stop_multiple: float = 2.0
    atr_take_multiple: float = 3.0
    hard_stop_pct: float = 0.07
    risk_budget_pct: float = 0.01
    max_position_pct: float = 0.12


def attach_risk_columns(frame: pd.DataFrame, params: RiskParams | None = None) -> pd.DataFrame:
    cfg = params or RiskParams()
    out = frame.copy()
    atr_stop = out["close"] - out["atr14"] * cfg.atr_stop_multiple
    pct_stop = out["close"] * (1 - cfg.hard_stop_pct)
    out["stop_price"] = pd.concat([atr_stop, pct_stop], axis=1).max(axis=1)
    out["take_profit_price"] = out["close"] + out["atr14"] * cfg.atr_take_multiple
    out["stop_loss_pct"] = (out["close"] - out["stop_price"]) / out["close"]
    out["take_profit_pct"] = (out["take_profit_price"] - out["close"]) / out["close"]
    out["position_weight_cap"] = (cfg.risk_budget_pct / out["stop_loss_pct"]).clip(upper=cfg.max_position_pct)
    out.loc[out["stop_loss_pct"] <= 0, "position_weight_cap"] = 0
    return out

