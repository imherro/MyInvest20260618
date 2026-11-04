import json

import pandas as pd

from shortterm_trader.cli import main


def test_intraday_watch_updates_status_without_reports_by_default(tmp_path, monkeypatch) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
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
            }
        ]
    ).to_csv(reports_dir / "plan_20260616_090000.csv", index=False, encoding="utf-8-sig")
    (data_dir / "qmt_realtime.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-06-16T13:00:00",
                "ticks": {
                    "000001.SZ": {"lastPrice": 11.4, "open": 11.0, "timetag": "20260616 13:00:00"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["intraday-watch", "--iterations", "2", "--interval", "0"]) == 0

    alerts = (data_dir / "intraday_alerts.jsonl").read_text(encoding="utf-8").splitlines()
    status = json.loads((data_dir / "intraday_status.json").read_text(encoding="utf-8"))
    assert len(alerts) == 1
    assert status["triggered"] == 1
    assert status["new_alerts"] == 0
    assert list(reports_dir.glob("intraday_*.csv")) == []
