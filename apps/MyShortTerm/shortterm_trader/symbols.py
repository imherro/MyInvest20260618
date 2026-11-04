from __future__ import annotations

import re

A_SHARE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$", re.IGNORECASE)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def is_a_share(symbol: str) -> bool:
    return bool(A_SHARE_RE.match(normalize_symbol(symbol)))


def to_baostock_code(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    code, market = normalized.split(".")
    if market == "SH":
        return f"sh.{code}"
    if market == "SZ":
        return f"sz.{code}"
    if market == "BJ":
        return f"bj.{code}"
    raise ValueError(f"Unsupported A-share market suffix: {symbol}")


def from_baostock_code(code: str) -> str:
    market, raw_code = code.strip().lower().split(".")
    suffix = {"sh": "SH", "sz": "SZ", "bj": "BJ"}.get(market)
    if suffix is None:
        raise ValueError(f"Unsupported BaoStock market prefix: {code}")
    return f"{raw_code}.{suffix}"

