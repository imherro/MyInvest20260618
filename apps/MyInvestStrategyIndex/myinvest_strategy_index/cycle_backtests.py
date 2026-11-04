from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from myinvest_strategy_index.config import Settings


DEFAULT_CYCLE_BACKTEST_RELATIVE_PATH = Path("MyInvestCycle") / "data" / "strategy_backtests"


@dataclass(frozen=True)
class CycleBacktestSummary:
    strategy_id: str
    strategy_name: str
    short_name: str
    category: str
    description: str
    start_date: str
    end_date: str
    sessions: int
    rebalance_count: int
    total_return: float | None
    annualized_return: float | None
    max_drawdown: float | None
    sharpe: float | None
    calmar: float | None
    alpha_vs_equal_weight: float | None
    average_turnover: float | None
    latest_signal: str
    latest_signal_date: str
    latest_weights: dict[str, float]
    source_file: str

    def as_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "short_name": self.short_name,
            "category": self.category,
            "description": self.description,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "sessions": self.sessions,
            "rebalance_count": self.rebalance_count,
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "max_drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "calmar": self.calmar,
            "alpha_vs_equal_weight": self.alpha_vs_equal_weight,
            "average_turnover": self.average_turnover,
            "latest_signal": self.latest_signal,
            "latest_signal_date": self.latest_signal_date,
            "latest_weights": self.latest_weights,
            "source_file": self.source_file,
        }


def default_cycle_backtest_dir(settings: Settings) -> Path:
    configured = os.getenv("MYINVEST_CYCLE_BACKTEST_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (settings.root.parent / DEFAULT_CYCLE_BACKTEST_RELATIVE_PATH).resolve()


def get_cycle_backtest_index(settings: Settings, *, backtest_dir: Path | None = None) -> dict[str, object]:
    directory = (backtest_dir or default_cycle_backtest_dir(settings)).resolve()
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    summaries: list[CycleBacktestSummary] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            data = _read_json(path)
            summaries.append(_summary_from_payload(path, data))
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    summaries = sorted(
        summaries,
        key=lambda item: (
            item.category,
            -(item.calmar if item.calmar is not None and math.isfinite(item.calmar) else -math.inf),
            item.strategy_id,
        ),
    )
    return {
        "ok": True,
        "source": "MyInvestCycle data/strategy_backtests",
        "source_dir": str(directory),
        "count": len(summaries),
        "strategies": [item.as_dict() for item in summaries],
        "errors": errors,
    }


def get_cycle_backtest_detail(
    settings: Settings,
    strategy_id: str,
    *,
    backtest_dir: Path | None = None,
) -> dict[str, object]:
    clean_id = _clean_strategy_id(strategy_id)
    directory = (backtest_dir or default_cycle_backtest_dir(settings)).resolve()
    path = directory / f"{clean_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Cycle backtest result not found: {clean_id}")
    data = _read_json(path)
    summary = _summary_from_payload(path, data)
    return {
        "ok": True,
        "source": "MyInvestCycle data/strategy_backtests",
        "source_dir": str(directory),
        "summary": summary.as_dict(),
        "metadata": data.get("metadata", {}),
        "performance_metrics": data.get("performance_metrics", {}),
        "validation": data.get("validation", {}),
        "comparison_assets": _comparison_assets(data),
        "equity_curve": data.get("equity_curve", []),
        "daily_returns": data.get("daily_returns", []),
        "signals": data.get("signals", []),
        "indicator_curve": data.get("indicator_curve", []),
        "cycle_blocks": data.get("cycle_blocks", []),
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("backtest JSON root must be an object")
    return data


def _summary_from_payload(path: Path, data: dict[str, Any]) -> CycleBacktestSummary:
    summary = _dict(data.get("summary"))
    metadata = _dict(data.get("metadata"))
    strategy_id = str(summary.get("strategy_id") or metadata.get("strategy_id") or path.stem)
    strategy_name = str(summary.get("strategy_name") or metadata.get("engine") or strategy_id)
    short_name = str(summary.get("short_name") or strategy_name)
    total_return = _float(summary.get("strategy_total_return"))
    sessions = _int(summary.get("sessions"))
    annualized_return = _float(summary.get("annualized_return"))
    if annualized_return is None and total_return is not None and sessions > 0:
        annualized_return = (1.0 + total_return) ** (252.0 / sessions) - 1.0
    max_drawdown = _float(summary.get("max_drawdown"))
    sharpe = _float(summary.get("sharpe"))
    calmar = _float(summary.get("calmar"))
    if calmar is None and annualized_return is not None and max_drawdown not in {None, 0.0}:
        calmar = annualized_return / abs(float(max_drawdown))
    return CycleBacktestSummary(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        short_name=short_name,
        category=_strategy_category(strategy_id),
        description=str(metadata.get("description") or ""),
        start_date=str(summary.get("start_date") or ""),
        end_date=str(summary.get("end_date") or ""),
        sessions=sessions,
        rebalance_count=_int(summary.get("rebalance_count")),
        total_return=total_return,
        annualized_return=annualized_return,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        calmar=calmar,
        alpha_vs_equal_weight=_float(summary.get("alpha_vs_equal_weight")),
        average_turnover=_float(summary.get("average_turnover")),
        latest_signal=str(summary.get("latest_signal") or ""),
        latest_signal_date=str(summary.get("latest_signal_date") or ""),
        latest_weights=_weights(summary.get("latest_weights")),
        source_file=path.name,
    )


def _comparison_assets(data: dict[str, Any]) -> list[dict[str, object]]:
    summary = _dict(data.get("summary"))
    candidates = summary.get("metric_comparison_assets") or summary.get("comparison_assets") or []
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _clean_strategy_id(strategy_id: str) -> str:
    clean = strategy_id.strip()
    if not clean or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in clean):
        raise ValueError("invalid strategy id")
    return clean


def _strategy_category(strategy_id: str) -> str:
    if strategy_id in {"all-weather", "four-asset"}:
        return "资产配置"
    if strategy_id in {"defensive-dividend", "industry-momentum"}:
        return "ETF轮动"
    if strategy_id.startswith("free-cash-flow"):
        return "自由现金流"
    if "reversion" in strategy_id or "drawdown" in strategy_id:
        return "回归/回撤"
    return "其他策略"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: object) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _weights(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        number = _float(raw)
        if number is not None:
            result[str(key)] = number
    return result
