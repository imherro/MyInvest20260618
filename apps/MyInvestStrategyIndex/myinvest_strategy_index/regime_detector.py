from __future__ import annotations

import pandas as pd


DEFAULT_EQUITY_CODE = "CN2296.CNI"
DEFAULT_BOND_CODE = "511260.SH"
DEFAULT_GOLD_CODE = "518880.SH"

RISK_OFF = -1
NEUTRAL = 0
RISK_ON = 1


def compute_regime_signals(
    prices: pd.DataFrame,
    *,
    equity_code: str = DEFAULT_EQUITY_CODE,
    bond_code: str = DEFAULT_BOND_CODE,
    momentum_window: int = 120,
    volatility_window: int = 20,
    volatility_baseline_window: int = 120,
) -> pd.DataFrame:
    """Compute past-only signals used by the regime detector."""
    _validate_inputs(
        prices,
        equity_code=equity_code,
        bond_code=bond_code,
        momentum_window=momentum_window,
        volatility_window=volatility_window,
        volatility_baseline_window=volatility_baseline_window,
    )
    aligned = prices.sort_index()
    equity = pd.to_numeric(aligned[equity_code], errors="coerce").ffill()
    bond = pd.to_numeric(aligned[bond_code], errors="coerce").ffill()
    equity_returns = equity.pct_change()

    equity_momentum = equity.pct_change(momentum_window).shift(1)
    equity_volatility = (
        equity_returns.rolling(volatility_window, min_periods=volatility_window).std().shift(1)
    )
    volatility_baseline = equity_volatility.rolling(
        volatility_baseline_window,
        min_periods=volatility_window,
    ).median()
    bond_trend = bond.pct_change(momentum_window).shift(1)

    return pd.DataFrame(
        {
            "equity_momentum": equity_momentum,
            "equity_volatility": equity_volatility,
            "volatility_baseline": volatility_baseline,
            "bond_trend": bond_trend,
        },
        index=aligned.index,
    )


def detect_regime(
    prices: pd.DataFrame,
    *,
    equity_code: str = DEFAULT_EQUITY_CODE,
    bond_code: str = DEFAULT_BOND_CODE,
    momentum_window: int = 120,
    volatility_window: int = 20,
    volatility_baseline_window: int = 120,
) -> pd.Series:
    """Return a past-only regime series aligned to the price index.

    Regime values:
    - 1: Risk-On
    - 0: Neutral
    - -1: Risk-Off

    The regime for each date uses signals shifted by one row, so the current
    day's close cannot affect the current day's regime.
    """
    signals = compute_regime_signals(
        prices,
        equity_code=equity_code,
        bond_code=bond_code,
        momentum_window=momentum_window,
        volatility_window=volatility_window,
        volatility_baseline_window=volatility_baseline_window,
    )
    regime = pd.Series(NEUTRAL, index=signals.index, name="regime", dtype="int8")

    volatility_low = signals["equity_volatility"] <= signals["volatility_baseline"]
    volatility_high = signals["equity_volatility"] > signals["volatility_baseline"]
    risk_on = (signals["equity_momentum"] > 0) & volatility_low
    risk_off = (signals["equity_momentum"] < 0) & volatility_high

    regime.loc[risk_on.fillna(False)] = RISK_ON
    regime.loc[risk_off.fillna(False)] = RISK_OFF
    return regime


def _validate_inputs(
    prices: pd.DataFrame,
    *,
    equity_code: str,
    bond_code: str,
    momentum_window: int,
    volatility_window: int,
    volatility_baseline_window: int,
) -> None:
    if prices.empty:
        raise ValueError("prices must not be empty")
    missing = [code for code in (equity_code, bond_code) if code not in prices.columns]
    if missing:
        raise KeyError(f"prices missing required columns: {', '.join(missing)}")
    if momentum_window < 1:
        raise ValueError("momentum_window must be positive")
    if volatility_window < 2:
        raise ValueError("volatility_window must be at least 2")
    if volatility_baseline_window < volatility_window:
        raise ValueError("volatility_baseline_window must be >= volatility_window")
