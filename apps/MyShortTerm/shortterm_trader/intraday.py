from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


MONITORED_ACTIONS = {"candidate", "watch_if_trigger"}
ALERT_STATUSES = {"triggered", "invalidated", "gap_skip"}


def latest_plan_path(reports_dir: Path) -> Path | None:
    plans = sorted(reports_dir.glob("plan_*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return plans[0] if plans else None


def load_plan(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def build_intraday_monitor(plan: pd.DataFrame, snapshot: dict[str, Any] | None) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ticks = snapshot.get("ticks", {}) if snapshot else {}
    snapshot_time = str(snapshot.get("updated_at", "")) if snapshot else ""

    for item in plan.to_dict("records"):
        symbol = str(item.get("symbol", "")).strip().upper()
        tick = ticks.get(symbol, {}) if isinstance(ticks, dict) else {}
        row = _monitor_row(item, tick if isinstance(tick, dict) else {}, snapshot_time)
        rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    rank = {"triggered": 0, "invalidated": 1, "gap_skip": 2, "waiting": 3, "no_tick": 4, "not_monitoring": 5}
    frame["_rank"] = frame["intraday_status"].map(rank).fillna(9)
    frame = frame.sort_values(["_rank", "score"], ascending=[True, False]).drop(columns=["_rank"])
    return frame.reset_index(drop=True)


def write_intraday_reports(monitor: pd.DataFrame, reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = reports_dir / f"intraday_{stamp}.csv"
    md_path = reports_dir / f"intraday_{stamp}.md"
    monitor.to_csv(csv_path, index=False, encoding="utf-8-sig")
    md_path.write_text(render_intraday_markdown(monitor), encoding="utf-8")
    return csv_path, md_path


def append_intraday_alerts(
    monitor: pd.DataFrame,
    plan_path: Path,
    log_path: Path,
    observed_at: datetime | None = None,
) -> list[dict[str, object]]:
    if monitor.empty:
        return []

    existing_keys = {str(item.get("dedupe_key", "")) for item in read_intraday_alerts(log_path)}
    now = (observed_at or datetime.now()).isoformat(timespec="seconds")
    plan_id = plan_path.stem
    new_alerts: list[dict[str, object]] = []
    for row in monitor.to_dict("records"):
        status = str(row.get("intraday_status", ""))
        if status not in ALERT_STATUSES:
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        dedupe_key = f"{plan_id}|{symbol}|{status}"
        if dedupe_key in existing_keys:
            continue
        alert = {
            "observed_at": now,
            "dedupe_key": dedupe_key,
            "plan_id": plan_id,
            "plan_file": plan_path.name,
            "symbol": symbol,
            "name": _json_value(row.get("name")),
            "status": status,
            "plan_action": _json_value(row.get("plan_action")),
            "last_price": _json_value(row.get("last_price")),
            "open": _json_value(row.get("open")),
            "trigger_price": _json_value(row.get("trigger_price")),
            "invalid_price": _json_value(row.get("invalid_price")),
            "max_open_price": _json_value(row.get("max_open_price")),
            "qmt_time": _json_value(row.get("qmt_time")),
            "snapshot_time": _json_value(row.get("snapshot_time")),
            "message": _alert_message(row),
        }
        new_alerts.append(alert)
        existing_keys.add(dedupe_key)

    if new_alerts:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for alert in new_alerts:
                fh.write(json.dumps(alert, ensure_ascii=False) + "\n")
    return new_alerts


def read_intraday_alerts(log_path: Path, limit: int | None = None) -> list[dict[str, object]]:
    if not log_path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    if limit is not None:
        records = records[-limit:]
    return list(reversed(records))


def write_intraday_status(
    monitor: pd.DataFrame,
    plan_path: Path,
    snapshot: dict[str, Any] | None,
    status_path: Path,
    alerts: list[dict[str, object]] | None = None,
    checked_at: datetime | None = None,
) -> dict[str, object]:
    now = (checked_at or datetime.now()).isoformat(timespec="seconds")
    counts = _status_counts(monitor)
    payload: dict[str, object] = {
        "checked_at": now,
        "plan_file": plan_path.name,
        "plan_path": str(plan_path),
        "snapshot_updated_at": str(snapshot.get("updated_at", "")) if snapshot else "",
        "rows": int(len(monitor)),
        "triggered": counts.get("triggered", 0),
        "invalidated": counts.get("invalidated", 0),
        "gap_skip": counts.get("gap_skip", 0),
        "waiting": counts.get("waiting", 0),
        "no_tick": counts.get("no_tick", 0),
        "not_monitoring": counts.get("not_monitoring", 0),
        "new_alerts": len(alerts or []),
        "alerts": alerts or [],
        "monitor": _json_records(monitor),
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def read_intraday_status(status_path: Path) -> dict[str, object] | None:
    if not status_path.exists():
        return None
    try:
        item = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return item if isinstance(item, dict) else None


def render_intraday_markdown(monitor: pd.DataFrame) -> str:
    lines = [
        "# Intraday Monitor",
        "",
        "Research alert output only. No orders are placed.",
        "",
    ]
    if monitor.empty:
        lines.append("No rows.")
        return "\n".join(lines) + "\n"
    view = monitor.copy()
    for column in ["distance_to_trigger_pct", "distance_to_invalid_pct"]:
        if column in view:
            view[column] = view[column].map(lambda value: f"{float(value):.2%}" if pd.notna(value) else "")
    for column in ["last_price", "open", "trigger_price", "invalid_price", "max_open_price"]:
        if column in view:
            view[column] = view[column].map(lambda value: f"{float(value):.3f}" if pd.notna(value) else "")
    columns = [
        "symbol",
        "name",
        "plan_action",
        "intraday_status",
        "last_price",
        "trigger_price",
        "invalid_price",
        "max_open_price",
        "distance_to_trigger_pct",
        "distance_to_invalid_pct",
        "qmt_time",
        "note",
    ]
    lines.extend(_markdown_table(view[[column for column in columns if column in view.columns]]))
    return "\n".join(lines) + "\n"


def _monitor_row(plan_row: dict[str, object], tick: dict[str, Any], snapshot_time: str) -> dict[str, object]:
    symbol = str(plan_row.get("symbol", "")).strip().upper()
    action = str(plan_row.get("action", "")).strip()
    last_price = _float_or_none(tick.get("lastPrice", tick.get("last_price", tick.get("price"))))
    open_price = _float_or_none(tick.get("open"))
    trigger_price = _float_or_none(plan_row.get("trigger_price"))
    invalid_price = _float_or_none(plan_row.get("invalid_price"))
    max_open_price = _float_or_none(plan_row.get("max_open_price"))
    status, note = _status(action, last_price, open_price, trigger_price, invalid_price, max_open_price, bool(tick))

    return {
        "symbol": symbol,
        "name": plan_row.get("name", ""),
        "plan_date": plan_row.get("date", ""),
        "plan_action": action,
        "intraday_status": status,
        "score": int(_float_or_none(plan_row.get("score")) or 0),
        "last_price": last_price,
        "open": open_price,
        "trigger_price": trigger_price,
        "invalid_price": invalid_price,
        "max_open_price": max_open_price,
        "distance_to_trigger_pct": _distance(last_price, trigger_price),
        "distance_to_invalid_pct": _distance(last_price, invalid_price),
        "qmt_time": str(tick.get("timetag", tick.get("time", snapshot_time))) if tick else "",
        "snapshot_time": snapshot_time,
        "note": note,
    }


def _status(
    action: str,
    last_price: float | None,
    open_price: float | None,
    trigger_price: float | None,
    invalid_price: float | None,
    max_open_price: float | None,
    has_tick: bool,
) -> tuple[str, str]:
    if action not in MONITORED_ACTIONS:
        return "not_monitoring", "plan row is not an active watch item"
    if not has_tick or last_price is None:
        return "no_tick", "no QMT tick for symbol"
    if max_open_price and open_price and open_price > max_open_price:
        return "gap_skip", "open price exceeded max_open_price"
    if invalid_price and last_price <= invalid_price:
        return "invalidated", "last price is at or below invalid_price"
    if trigger_price and last_price >= trigger_price:
        return "triggered", "last price reached trigger_price"
    return "waiting", "not triggered"


def _distance(price: float | None, threshold: float | None) -> float | None:
    if price is None or threshold is None or threshold == 0:
        return None
    return price / threshold - 1


def _float_or_none(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def _status_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty or "intraday_status" not in frame:
        return {}
    counts = frame["intraday_status"].value_counts()
    return {str(status): int(count) for status, count in counts.items()}


def _alert_message(row: dict[str, object]) -> str:
    status = str(row.get("intraday_status", ""))
    symbol = str(row.get("symbol", "")).strip().upper()
    if status == "triggered":
        return f"{symbol} reached trigger price"
    if status == "invalidated":
        return f"{symbol} reached invalid price"
    if status == "gap_skip":
        return f"{symbol} opened above max open price"
    return f"{symbol} status changed to {status}"


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
