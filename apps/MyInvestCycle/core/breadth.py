from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import CACHE_DIR
from core.data_loader import get_tushare_pro, normalize_trade_date


MARKET_DAILY_COLUMNS = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


def _cache_path(trade_date: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / f"market_daily_{trade_date}.csv"


def _stock_cache_path(ts_code: str, start_date: str, end_date: str, cache_dir: Path = CACHE_DIR) -> Path:
    safe_code = ts_code.replace(".", "_")
    return cache_dir / "stock_daily" / f"{safe_code}_{start_date}_{end_date}.csv"


def _coerce_market_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=MARKET_DAILY_COLUMNS)

    result = df.copy()
    for column in MARKET_DAILY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    result = result[MARKET_DAILY_COLUMNS]
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    numeric_columns = [col for col in MARKET_DAILY_COLUMNS if col not in {"ts_code", "trade_date"}]
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    return result.dropna(subset=["ts_code", "trade_date", "pct_chg"]).reset_index(drop=True)


def fetch_market_daily(trade_date: str, *, token: str | None = None) -> pd.DataFrame:
    date_text = normalize_trade_date(trade_date)
    pro = get_tushare_pro(token)
    raw = pro.daily(trade_date=date_text)
    return _coerce_market_daily(raw)


def get_market_daily(
    trade_date: str,
    *,
    refresh: bool = False,
    token: str | None = None,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    date_text = normalize_trade_date(trade_date)
    path = _cache_path(date_text, cache_dir)
    if path.exists() and not refresh:
        return _coerce_market_daily(pd.read_csv(path, dtype={"trade_date": str}))

    df = fetch_market_daily(date_text, token=token)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    return df


def fetch_stock_daily(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    token: str | None = None,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    pro = get_tushare_pro(token)
    raw = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
    return _coerce_market_daily(raw)


def get_stock_daily(
    ts_code: str,
    start_date: str,
    end_date: str,
    *,
    refresh: bool = False,
    token: str | None = None,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    path = _stock_cache_path(ts_code, start, end, cache_dir)
    if path.exists() and not refresh:
        return _coerce_market_daily(pd.read_csv(path, dtype={"trade_date": str}))

    df = fetch_stock_daily(ts_code, start, end, token=token)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    return df


def get_market_history_sample(
    market_daily_df: pd.DataFrame,
    start_date: str,
    end_date: str,
    *,
    sample_size: int = 30,
    token: str | None = None,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    """Build a lightweight 52-week breadth sample from high-turnover stocks."""
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    daily = _coerce_market_daily(market_daily_df)
    if daily.empty or sample_size <= 0:
        return pd.DataFrame(columns=MARKET_DAILY_COLUMNS)

    ranked = daily.sort_values("amount", ascending=False).head(sample_size)
    frames: list[pd.DataFrame] = []
    for ts_code in ranked["ts_code"].dropna().astype(str):
        try:
            stock_df = get_stock_daily(
                ts_code,
                start,
                end,
                token=token,
                cache_dir=cache_dir,
            )
        except Exception:
            continue
        if not stock_df.empty:
            frames.append(stock_df)

    if not frames:
        return pd.DataFrame(columns=MARKET_DAILY_COLUMNS)
    return _coerce_market_daily(pd.concat(frames, ignore_index=True))


def calc_52_week_high_ratio(
    market_history_df: pd.DataFrame,
    *,
    trade_date: str | None = None,
    lookback: int = 252,
) -> float:
    """Calculate the ratio of stocks closing at their lookback high."""
    history = _coerce_market_daily(market_history_df)
    if history.empty:
        return 0.0

    if trade_date is None:
        date_text = str(history["trade_date"].max())
    else:
        date_text = normalize_trade_date(trade_date)

    history = history[history["trade_date"] <= date_text].copy()
    history = history.sort_values(["ts_code", "trade_date"])
    recent = history.groupby("ts_code").tail(lookback)
    highs = recent.groupby("ts_code")["close"].max()
    latest = history[history["trade_date"] == date_text].set_index("ts_code")

    aligned = latest.join(highs.rename("high_52w"), how="inner")
    if aligned.empty:
        return 0.0
    return float((aligned["close"] >= aligned["high_52w"]).mean())


def limit_up_down(market_daily_df: pd.DataFrame) -> dict[str, int | float]:
    daily = _coerce_market_daily(market_daily_df)
    total = int(len(daily))
    if total == 0:
        return {
            "total": 0,
            "up_count": 0,
            "down_count": 0,
            "limit_up_count": 0,
            "up_down_ratio": 0.0,
            "limit_up_ratio": 0.0,
        }

    up_count = int((daily["pct_chg"] > 0).sum())
    down_count = int((daily["pct_chg"] < 0).sum())
    limit_up_count = int((daily["pct_chg"] >= 9.5).sum())

    return {
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "limit_up_count": limit_up_count,
        "up_down_ratio": round(up_count / total, 4),
        "limit_up_ratio": round(limit_up_count / total, 4),
    }


def calculate_breadth_metrics(
    market_daily_df: pd.DataFrame,
    *,
    market_history_df: pd.DataFrame | None = None,
) -> dict[str, float | int]:
    counts = limit_up_down(market_daily_df)
    total = int(counts["total"])
    if total == 0:
        return {
            **counts,
            "high_52w_ratio": 0.0,
            "strength_score": 0.0,
        }

    daily = _coerce_market_daily(market_daily_df)
    if market_history_df is not None and not market_history_df.empty:
        high_52w_ratio = calc_52_week_high_ratio(
            market_history_df,
            trade_date=str(daily["trade_date"].max()),
        )
    else:
        # Simplified high-strength proxy for Task 2 when full stock history is absent.
        high_52w_ratio = float(((daily["pct_chg"] >= 5.0) & (daily["close"] >= daily["high"] * 0.995)).mean())

    up_down_score = float(counts["up_down_ratio"])
    limit_score = min(float(counts["limit_up_ratio"]) / 0.08, 1.0)
    high_score = min(high_52w_ratio / 0.12, 1.0)
    strength_score = 0.70 * up_down_score + 0.15 * limit_score + 0.15 * high_score

    return {
        **counts,
        "high_52w_ratio": round(high_52w_ratio, 4),
        "strength_score": round(max(0.0, min(1.0, strength_score)), 4),
    }
