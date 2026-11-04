from __future__ import annotations

import pandas as pd

from myinvest_strategy_index.regime_detector import NEUTRAL, RISK_OFF, RISK_ON


EQUITY_CODE = "399606.SZ"
FREE_CASH_FLOW_CODE = "480092.CNI"
GOLD_CODE = "518880.SH"
BOND_CODE = "511260.SH"

ASSET_CODES: tuple[str, ...] = (
    EQUITY_CODE,
    FREE_CASH_FLOW_CODE,
    GOLD_CODE,
    BOND_CODE,
)

REGIME_WEIGHTS: dict[int, dict[str, float]] = {
    RISK_ON: {
        EQUITY_CODE: 0.50,
        FREE_CASH_FLOW_CODE: 0.30,
        GOLD_CODE: 0.10,
        BOND_CODE: 0.10,
    },
    NEUTRAL: {
        EQUITY_CODE: 0.15,
        FREE_CASH_FLOW_CODE: 0.40,
        GOLD_CODE: 0.20,
        BOND_CODE: 0.25,
    },
    RISK_OFF: {
        EQUITY_CODE: 0.05,
        FREE_CASH_FLOW_CODE: 0.15,
        GOLD_CODE: 0.35,
        BOND_CODE: 0.45,
    },
}


def get_dynamic_weights(regime: pd.Series) -> pd.DataFrame:
    """Map a regime series to monthly-rebalanced four-asset weights.

    The month-end sampled regime is forward-filled to later dates. This keeps
    intra-month signal noise from changing weights before the next monthly
    rebalance point and avoids using a future month-end state inside that month.
    """
    if regime.empty:
        return pd.DataFrame(columns=ASSET_CODES, index=regime.index, dtype=float)

    clean_regime = _clean_regime(regime)
    monthly_regime = clean_regime.resample("ME").last()
    applied_regime = monthly_regime.reindex(clean_regime.index, method="ffill").fillna(NEUTRAL).astype("int8")

    rows = [_weights_for_regime(value) for value in applied_regime]
    weights = pd.DataFrame(rows, index=clean_regime.index, columns=ASSET_CODES, dtype=float)
    _validate_weights(weights)
    return weights


def _clean_regime(regime: pd.Series) -> pd.Series:
    clean = pd.to_numeric(regime.sort_index(), errors="coerce")
    clean = clean.where(clean.isin(REGIME_WEIGHTS), NEUTRAL)
    return clean.fillna(NEUTRAL).astype("int8")


def _weights_for_regime(value: int) -> dict[str, float]:
    return REGIME_WEIGHTS.get(int(value), REGIME_WEIGHTS[NEUTRAL])


def _validate_weights(weights: pd.DataFrame) -> None:
    if weights.isna().any().any():
        raise RuntimeError("dynamic weights contain NaN")
    sums = weights.sum(axis=1)
    if not sums.empty and not (sums.sub(1.0).abs() <= 1e-12).all():
        raise RuntimeError("dynamic weights must sum to 1")
