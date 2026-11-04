from __future__ import annotations

from typing import Any

MIN_LATEST_AMOUNT = 30_000.0
MIN_TURNOVER_RATE = 0.5
MAX_DAILY_VOLATILITY = 0.06


def assess_tradability(position: dict[str, Any]) -> dict[str, Any]:
    code = str(position.get("code") or "")
    name = str(position.get("name") or "")
    metrics = position.get("metrics") or {}
    threshold = _daily_limit_threshold(code, name)
    latest_pct_chg = _to_float(metrics.get("latest_pct_chg"))
    latest_amount = _to_float(metrics.get("latest_amount"))
    turnover_rate = _to_float(metrics.get("turnover_rate"))
    volatility_20d = _to_float(metrics.get("volatility_20d"))

    checks = {
        "not_st": not _is_st_name(name),
        "not_limit_up": _below_limit(latest_pct_chg, threshold),
        "not_limit_down": _above_limit(latest_pct_chg, threshold),
        "liquidity_ok": _is_at_least(latest_amount, MIN_LATEST_AMOUNT),
        "turnover_ok": _is_at_least(turnover_rate, MIN_TURNOVER_RATE),
        "volatility_ok": volatility_20d is None or volatility_20d <= MAX_DAILY_VOLATILITY,
        "no_price_spike": latest_pct_chg is None or abs(latest_pct_chg) < threshold * 0.85,
    }
    reasons = _failed_reasons(checks)
    return {
        "tradable": all(checks.values()),
        "checks": checks,
        "reasons": reasons,
        "limit_threshold": threshold,
        "liquidity_threshold": MIN_LATEST_AMOUNT,
        "turnover_threshold": MIN_TURNOVER_RATE,
    }


def _daily_limit_threshold(code: str, name: str) -> float:
    symbol, exchange = _split_code(code)
    if _is_st_name(name):
        return 5.0
    if exchange == "BJ":
        return 30.0
    if exchange == "SH" and symbol.startswith(("688", "689")):
        return 20.0
    if exchange == "SZ" and symbol.startswith(("300", "301")):
        return 20.0
    return 10.0


def _split_code(code: str) -> tuple[str, str]:
    if "." not in code:
        return code, ""
    symbol, exchange = code.rsplit(".", 1)
    return symbol, exchange


def _is_st_name(name: str) -> bool:
    normalized = name.upper().strip()
    st_prefixes = ("ST", "*ST", "S*ST", "S ST", "SST")
    return normalized.startswith(st_prefixes) or "退" in name


def _below_limit(value: float | None, threshold: float) -> bool:
    if value is None:
        return False
    return value < threshold * 0.98


def _above_limit(value: float | None, threshold: float) -> bool:
    if value is None:
        return False
    return value > -threshold * 0.98


def _is_at_least(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _failed_reasons(checks: dict[str, bool]) -> list[str]:
    labels = {
        "not_st": "ST or delisting risk",
        "not_limit_up": "near limit up",
        "not_limit_down": "near limit down",
        "liquidity_ok": "low latest amount",
        "turnover_ok": "low turnover",
        "volatility_ok": "volatility spike",
        "no_price_spike": "abnormal latest move",
    }
    return [labels[key] for key, passed in checks.items() if not passed]
