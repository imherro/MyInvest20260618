from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def fit_linear_factor_model(
    frame: pd.DataFrame,
    *,
    target_col: str,
    factor_cols: Iterable[str],
) -> dict[str, object]:
    factors = list(factor_cols)
    clean = frame[[target_col, *factors]].dropna().copy()
    if len(clean) <= len(factors) + 2:
        return {
            "available": False,
            "reason": "insufficient aligned observations",
            "observations": len(clean),
            "factors": factors,
        }
    y = clean[target_col].astype(float).to_numpy()
    x = clean[factors].astype(float).to_numpy()
    design = np.column_stack([np.ones(len(clean)), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coef
    residual = y - fitted
    ss_total = float(((y - y.mean()) ** 2).sum())
    ss_resid = float((residual ** 2).sum())
    r_squared = None if ss_total == 0 else 1.0 - ss_resid / ss_total
    betas = {factor: round(float(value), 6) for factor, value in zip(factors, coef[1:])}
    factor_part = x @ coef[1:]
    neutralized = y - factor_part
    return {
        "available": True,
        "observations": len(clean),
        "start": str(clean.index.min()),
        "end": str(clean.index.max()),
        "target_col": target_col,
        "factors": factors,
        "intercept_daily": round(float(coef[0]), 8),
        "intercept_annualized_linear": round(float(coef[0]) * 252.0, 6),
        "betas": betas,
        "r_squared": None if r_squared is None else round(float(r_squared), 6),
        "factor_contribution_sum": {
            factor: round(float((clean[factor].astype(float).to_numpy() * beta).sum()), 6)
            for factor, beta in zip(factors, coef[1:])
        },
        "linear_return_sum": {
            "portfolio": round(float(y.sum()), 6),
            "factor_part": round(float(factor_part.sum()), 6),
            "neutralized_residual_alpha": round(float(neutralized.sum()), 6),
        },
        "neutralized_returns": neutralized.tolist(),
        "dates": [str(item) for item in clean.index.tolist()],
    }


def metrics_from_returns(dates: list[str], returns: Iterable[float]) -> dict[str, object]:
    values = [float(value) for value in returns]
    if len(values) < 2:
        return {}
    equity = pd.Series((1.0 + pd.Series(values)).cumprod())
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max((len(values) - 1) / 252.0, 1 / 252.0)
    cagr = (float(equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years)) - 1.0
    volatility = float(pd.Series(values).std() * math.sqrt(252.0))
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    sharpe = cagr / volatility if volatility else None
    calmar = cagr / abs(max_drawdown) if max_drawdown else None
    return {
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
        "observations": len(values),
        "total_return": round(total, 6),
        "cagr": round(cagr, 6),
        "volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": None if sharpe is None else round(float(sharpe), 6),
        "calmar": None if calmar is None else round(float(calmar), 6),
    }
