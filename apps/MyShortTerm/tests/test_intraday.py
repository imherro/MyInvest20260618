import pandas as pd

from shortterm_trader.intraday import (
    append_intraday_alerts,
    build_intraday_monitor,
    read_intraday_alerts,
    read_intraday_status,
    write_intraday_status,
)


def _plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "date": "2026-06-15",
                "action": "watch_if_trigger",
                "score": 65,
                "trigger_price": 11.39,
                "invalid_price": 10.63,
                "max_open_price": 11.45,
            },
            {
                "symbol": "510300.SH",
                "name": "沪深300ETF",
                "date": "2026-06-15",
                "action": "blocked",
                "score": 20,
                "trigger_price": 5.0,
                "invalid_price": 4.7,
                "max_open_price": 5.1,
            },
        ]
    )


def test_intraday_monitor_detects_triggered() -> None:
    snapshot = {
        "updated_at": "2026-06-16T13:00:00",
        "ticks": {
            "000001.SZ": {"lastPrice": 11.4, "open": 11.0, "timetag": "20260616 13:00:00"},
            "510300.SH": {"lastPrice": 4.9, "open": 4.9},
        },
    }
    result = build_intraday_monitor(_plan(), snapshot)
    first = result.loc[result["symbol"] == "000001.SZ"].iloc[0]
    assert first["intraday_status"] == "triggered"
    blocked = result.loc[result["symbol"] == "510300.SH"].iloc[0]
    assert blocked["intraday_status"] == "not_monitoring"


def test_intraday_monitor_detects_gap_skip_and_invalidated() -> None:
    plan = _plan().iloc[[0]].copy()
    gap = build_intraday_monitor(plan, {"ticks": {"000001.SZ": {"lastPrice": 11.5, "open": 11.5}}})
    assert gap.iloc[0]["intraday_status"] == "gap_skip"

    invalid = build_intraday_monitor(plan, {"ticks": {"000001.SZ": {"lastPrice": 10.5, "open": 11.0}}})
    assert invalid.iloc[0]["intraday_status"] == "invalidated"


def test_intraday_alerts_are_deduped_by_plan_symbol_and_status(tmp_path) -> None:
    plan_path = tmp_path / "plan_20260616_090000.csv"
    monitor = build_intraday_monitor(
        _plan().iloc[[0]].copy(),
        {"ticks": {"000001.SZ": {"lastPrice": 11.4, "open": 11.0, "timetag": "20260616 13:00:00"}}},
    )
    log_path = tmp_path / "intraday_alerts.jsonl"

    first = append_intraday_alerts(monitor, plan_path, log_path)
    second = append_intraday_alerts(monitor, plan_path, log_path)
    stored = read_intraday_alerts(log_path)

    assert len(first) == 1
    assert second == []
    assert len(stored) == 1
    assert stored[0]["symbol"] == "000001.SZ"
    assert stored[0]["status"] == "triggered"


def test_intraday_status_round_trip(tmp_path) -> None:
    plan_path = tmp_path / "plan_20260616_090000.csv"
    snapshot = {"updated_at": "2026-06-16T13:00:00", "ticks": {"000001.SZ": {"lastPrice": 11.4, "open": 11.0}}}
    monitor = build_intraday_monitor(_plan().iloc[[0]].copy(), snapshot)
    status_path = tmp_path / "intraday_status.json"

    payload = write_intraday_status(monitor, plan_path, snapshot, status_path, alerts=[{"symbol": "000001.SZ"}])
    stored = read_intraday_status(status_path)

    assert payload["triggered"] == 1
    assert payload["new_alerts"] == 1
    assert stored is not None
    assert stored["plan_file"] == "plan_20260616_090000.csv"
    assert stored["monitor"][0]["symbol"] == "000001.SZ"
