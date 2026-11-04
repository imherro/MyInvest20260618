from __future__ import annotations

import pandas as pd

from shortterm_trader.config import load_settings
from shortterm_trader.etf_compare import DEFAULT_INSTRUMENTS, _build_equal_weight_history, get_etf_compare_payload


def test_etf_compare_payload_reads_cached_histories(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    for instrument in DEFAULT_INSTRUMENTS:
        if instrument.kind == "synthetic_equal_weight":
            continue
        safe_code = instrument.code.replace(".", "_")
        (settings.cache_dir / f"etf_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1.000,1.000\n"
            "2021-01-05,1.050,1.050\n",
            encoding="utf-8",
        )

    payload = get_etf_compare_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == len(DEFAULT_INSTRUMENTS)
    assert "515590.SH" not in payload["series"]
    assert "480092.CNI" in payload["series"]
    assert "980092.CNI" not in payload["series"]
    assert "VIRTUAL_EQUAL_WEIGHT" in payload["series"]
    assert payload["series"]["512890.SH"][0]["date"] == "2021-01-04"
    assert payload["series"]["512890.SH"][1]["value"] == 1.05
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT"][0]["value"] == 1.0
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT"][1]["value"] == 1.05


def test_equal_weight_history_adds_later_etf_without_entry_jump() -> None:
    first = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"]),
            "close": [100.0, 110.0, 121.0],
            "value": [100.0, 110.0, 121.0],
        }
    )
    later = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-05", "2021-01-06"]),
            "close": [50.0, 55.0],
            "value": [50.0, 55.0],
        }
    )

    history = _build_equal_weight_history([first, later])

    assert history["date"].dt.strftime("%Y-%m-%d").tolist() == ["2021-01-04", "2021-01-05", "2021-01-06"]
    assert history["value"].round(6).tolist() == [1.0, 1.1, 1.21]
