from __future__ import annotations

import pandas as pd

from shortterm_trader.capital_migration import (
    DEFAULT_CAPITAL_INSTRUMENTS,
    get_capital_migration_payload,
    load_or_fetch_capital_history,
)
from shortterm_trader.config import load_settings


def test_capital_migration_payload_reads_cached_histories(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    _write_capital_caches(settings.cache_dir)

    payload = get_capital_migration_payload(settings, window=5)

    assert payload["ok"] is True
    assert payload["window"] == 5
    assert payload["benchmark"] == "000985.CSI"
    assert "价量承接代理" in payload["proxy_note"]
    assert "technology" in payload["bucket_metrics"]
    assert "dividend" in payload["bucket_metrics"]
    assert payload["bucket_metrics"]["technology"]["absorptionScore"] > payload["bucket_metrics"]["dividend"]["absorptionScore"]
    assert payload["bucket_metrics"]["dividend"]["outflowPressure"] > payload["bucket_metrics"]["technology"]["outflowPressure"]
    assert any(row["source"] == "dividend" and row["target"] == "technology" for row in payload["matrix"])
    assert payload["flows"]
    assert payload["leaders"]
    assert payload["series"]["technology"]


def test_capital_migration_defaults_unknown_window(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    _write_capital_caches(settings.cache_dir)

    payload = get_capital_migration_payload(settings, window=7)

    assert payload["window"] == 5


def test_capital_migration_loader_can_reuse_trend_cache(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    instrument = DEFAULT_CAPITAL_INSTRUMENTS[0]
    dates = pd.bdate_range("2026-01-02", periods=30)
    safe_code = instrument.code.replace(".", "_")
    pd.DataFrame({"date": dates, "close": range(100, 130), "value": range(100, 130)}).to_csv(
        settings.cache_dir / f"trend_channel_{safe_code}.csv",
        index=False,
        encoding="utf-8",
    )

    history = load_or_fetch_capital_history(settings, instrument)

    assert len(history) == 30
    assert {"date", "close", "value", "amount", "volume"} <= set(history.columns)


def _write_capital_caches(cache_dir) -> None:
    dates = pd.bdate_range("2026-03-02", periods=80)
    bucket_steps = {
        "broad": [0.001] * 72 + [0.001] * 8,
        "technology": [0.0005] * 72 + [0.008] * 8,
        "dividend": [0.0003] * 72 + [-0.006] * 8,
        "cyclical": [0.0004] * 72 + [0.004] * 8,
        "consumer_health": [0.0002] * 72 + [0.002] * 8,
        "defensive_cash": [0.0001] * 80,
    }
    for index, instrument in enumerate(DEFAULT_CAPITAL_INSTRUMENTS):
        value = 1000.0 + index * 8
        values = []
        for step in bucket_steps[instrument.bucket]:
            value *= 1 + step
            values.append(value)
        amount_base = 1000 + index * 5
        amount = [amount_base] * 72
        if instrument.bucket in {"technology", "dividend", "cyclical"}:
            amount.extend([amount_base * 1.9] * 8)
        else:
            amount.extend([amount_base] * 8)
        frame = pd.DataFrame(
            {
                "date": dates,
                "close": values,
                "value": values,
                "amount": amount,
                "volume": amount,
            }
        )
        safe_code = instrument.code.replace(".", "_")
        frame.to_csv(cache_dir / f"capital_migration_{safe_code}.csv", index=False, encoding="utf-8")
