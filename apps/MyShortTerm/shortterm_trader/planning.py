from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from shortterm_trader.strategy.short_term import StrategyParams, build_signal_frame
from shortterm_trader.symbols import is_a_share, normalize_symbol


@dataclass(frozen=True)
class TradeFilterParams:
    min_history: int = 60
    min_price: float = 2.0
    max_price: float = 300.0
    min_amount: float = 80_000_000.0
    max_stop_loss_pct: float = 0.08
    min_position_weight: float = 0.02
    watch_score: int = 55
    trigger_buffer_pct: float = 0.005
    max_open_gap_pct: float = 0.035


def build_next_day_plan(
    universe: list[dict[str, object]],
    bars_by_symbol: dict[str, pd.DataFrame],
    params: TradeFilterParams | None = None,
    strategy_params: StrategyParams | None = None,
) -> pd.DataFrame:
    cfg = params or TradeFilterParams()
    rows: list[dict[str, object]] = []
    for item in universe:
        symbol = normalize_symbol(str(item["symbol"]))
        bars = bars_by_symbol.get(symbol)
        if bars is None or bars.empty:
            rows.append(_blocked_row(item, symbol, "no_data"))
            continue
        try:
            signal_frame = build_signal_frame(bars, params=strategy_params)
            row = signal_frame.iloc[-1]
            reasons, tags = evaluate_trade_filters(row, len(bars), str(item.get("name", "")), cfg)
            action = _action(row, reasons, cfg)
            trigger_price = max(float(row["close"]) * (1 + cfg.trigger_buffer_pct), float(row.get("high_n_prev", 0) or 0))
            rows.append(
                {
                    "symbol": symbol,
                    "name": item.get("name", ""),
                    "date": row["date"],
                    "action": action,
                    "score": int(row["score"]),
                    "signal": bool(row["signal"]),
                    "setup": row["setup"],
                    "close": float(row["close"]),
                    "trigger_price": trigger_price,
                    "invalid_price": float(row["stop_price"]),
                    "take_profit_price": float(row["take_profit_price"]),
                    "stop_loss_pct": float(row["stop_loss_pct"]),
                    "position_weight_cap": float(row["position_weight_cap"]),
                    "max_open_price": float(row["close"]) * (1 + cfg.max_open_gap_pct),
                    "amount": float(row.get("amount", 0) or 0),
                    "source": row.get("source", ""),
                    "tags": "+".join(tags) if tags else "none",
                    "block_reasons": "; ".join(reasons),
                }
            )
        except Exception as exc:
            rows.append(_blocked_row(item, symbol, f"plan_error:{exc}"))

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    action_rank = {"candidate": 0, "watch_if_trigger": 1, "filtered": 2, "blocked": 3}
    frame["_rank"] = frame["action"].map(action_rank).fillna(9)
    frame = frame.sort_values(["_rank", "score", "amount"], ascending=[True, False, False]).drop(columns=["_rank"])
    return frame.reset_index(drop=True)


def evaluate_trade_filters(row: pd.Series, history_rows: int, name: str, params: TradeFilterParams) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    tags: list[str] = []
    symbol = normalize_symbol(str(row.get("symbol", "")))
    close = float(row.get("close", 0) or 0)
    amount = float(row.get("amount", 0) or 0)
    stop_loss_pct = float(row.get("stop_loss_pct", 0) or 0)
    position_weight = float(row.get("position_weight_cap", 0) or 0)

    if history_rows < params.min_history:
        reasons.append("history_too_short")
    if is_a_share(symbol) and ("ST" in name.upper() or "*ST" in name.upper()):
        reasons.append("risk_warning_name")
    if close < params.min_price:
        reasons.append("price_too_low")
    if close > params.max_price:
        reasons.append("price_too_high")
    if amount < params.min_amount:
        reasons.append("amount_too_low")
    if stop_loss_pct <= 0 or stop_loss_pct > params.max_stop_loss_pct:
        reasons.append("stop_too_wide")
    if position_weight < params.min_position_weight:
        reasons.append("position_too_small")

    if bool(row.get("trend_ok", False)):
        tags.append("trend")
    if bool(row.get("breakout_ok", False)):
        tags.append("breakout")
    if bool(row.get("volume_ok", False)):
        tags.append("volume")
    if bool(row.get("momentum_ok", False)):
        tags.append("momentum")
    if not reasons:
        tags.append("tradable")
    return reasons, tags


def write_plan_reports(plan: pd.DataFrame, reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = reports_dir / f"plan_{stamp}.csv"
    md_path = reports_dir / f"plan_{stamp}.md"
    plan.to_csv(csv_path, index=False, encoding="utf-8-sig")
    md_path.write_text(render_plan_markdown(plan), encoding="utf-8")
    return csv_path, md_path


def render_plan_markdown(plan: pd.DataFrame) -> str:
    lines = [
        "# Next-Day Plan",
        "",
        "Research output only. No orders are placed and no share or cash amount is suggested.",
        "",
    ]
    if plan.empty:
        lines.append("No symbols were evaluated.")
    else:
        view = plan.copy()
        for column in ["stop_loss_pct", "position_weight_cap"]:
            if column in view:
                view[column] = view[column].map(lambda x: f"{float(x):.2%}" if pd.notna(x) else "")
        for column in ["close", "trigger_price", "invalid_price", "take_profit_price", "max_open_price"]:
            if column in view:
                view[column] = view[column].map(lambda x: f"{float(x):.3f}" if pd.notna(x) else "")
        columns = [
            "symbol",
            "name",
            "date",
            "action",
            "score",
            "setup",
            "close",
            "trigger_price",
            "invalid_price",
            "stop_loss_pct",
            "position_weight_cap",
            "block_reasons",
        ]
        lines.extend(_markdown_table(view[[column for column in columns if column in view.columns]]))
    return "\n".join(lines) + "\n"


def _action(row: pd.Series, reasons: list[str], params: TradeFilterParams) -> str:
    score = int(row.get("score", 0) or 0)
    if reasons:
        return "filtered" if score >= params.watch_score else "blocked"
    if bool(row.get("signal", False)):
        return "candidate"
    if score >= params.watch_score:
        return "watch_if_trigger"
    return "blocked"


def _blocked_row(item: dict[str, object], symbol: str, reason: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": item.get("name", ""),
        "date": "",
        "action": "blocked",
        "score": 0,
        "signal": False,
        "setup": "none",
        "close": 0.0,
        "trigger_price": 0.0,
        "invalid_price": 0.0,
        "take_profit_price": 0.0,
        "stop_loss_pct": 0.0,
        "position_weight_cap": 0.0,
        "max_open_price": 0.0,
        "amount": 0.0,
        "source": "",
        "tags": "none",
        "block_reasons": reason,
    }


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    columns = [str(column) for column in frame.columns]
    rows = [["" if pd.isna(value) else str(value) for value in row] for row in frame.to_numpy()]
    widths = [
        max(len(columns[index]), *(len(row[index]) for row in rows)) if rows else len(columns[index])
        for index in range(len(columns))
    ]

    def render(values: list[str]) -> str:
        return "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(values)) + " |"

    output = [render(columns), "| " + " | ".join("-" * width for width in widths) + " |"]
    output.extend(render(row) for row in rows)
    return output
