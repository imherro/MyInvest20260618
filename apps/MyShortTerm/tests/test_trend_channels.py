from __future__ import annotations

import pandas as pd

from shortterm_trader.config import load_settings
from shortterm_trader.trend_channels import BROAD_TREND_INSTRUMENTS, get_trend_channel_payload


def test_trend_channel_payload_reads_cached_histories(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    dates = pd.bdate_range("2016-01-04", periods=80)
    for index, instrument in enumerate(BROAD_TREND_INSTRUMENTS):
        close = [1000 + index * 20 + day * 3 for day in range(len(dates))]
        frame = pd.DataFrame({"date": dates, "close": close, "value": close})
        safe_code = instrument.code.replace(".", "_")
        frame.to_csv(settings.cache_dir / f"trend_channel_{safe_code}.csv", index=False, encoding="utf-8")

    payload = get_trend_channel_payload(settings, "broad")

    assert payload["ok"] is True
    assert payload["fit"] == "since2016"
    assert not payload["errors"]
    assert len(payload["instruments"]) == len(BROAD_TREND_INSTRUMENTS)
    assert "000001.SH" in payload["series"]
    first_row = payload["series"]["000001.SH"][0]
    assert {"date", "close", "trend", "lower", "upper", "drawdown", "channelPosition"} <= set(first_row)
    summary = payload["summaries"]["000001.SH"]
    assert summary["name"] == "上证指数"
    assert summary["rows"] == 80
    assert summary["latestDate"] == dates[-1].strftime("%Y-%m-%d")
    assert "distanceToLower" in summary
    assert "annualizedTrend" in summary


def test_trend_channel_payload_rejects_unknown_channel(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")

    try:
        get_trend_channel_payload(settings, "missing")
    except ValueError as exc:
        assert "Unknown trend channel" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
