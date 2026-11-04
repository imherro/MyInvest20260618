from __future__ import annotations

from shortterm_trader.config import load_settings
from shortterm_trader.value_compare import (
    DEFAULT_VALUE_COMPARE_INSTRUMENTS,
    VALUE_COMPARE_BACKGROUND,
    get_value_compare_payload,
)


def test_value_compare_payload_reads_cached_histories_with_background(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    instruments = [*DEFAULT_VALUE_COMPARE_INSTRUMENTS, VALUE_COMPARE_BACKGROUND]
    for instrument in instruments:
        safe_code = instrument.code.replace(".", "_")
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            "2021-01-05,1050.000,1050.000\n",
            encoding="utf-8",
        )

    payload = get_value_compare_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == len(DEFAULT_VALUE_COMPARE_INSTRUMENTS)
    assert payload["background"]["code"] == "000001.SH"
    assert "h21052.CSI" in payload["series"]
    assert "CN2296.CNI" in payload["series"]
    assert "480081.CNI" not in payload["series"]
    assert "h20269.CSI" in payload["series"]
    assert "480092.CNI" in payload["series"]
    assert "VIRTUAL_EQUAL_WEIGHT_STRATEGY" in payload["series"]
    assert "VIRTUAL_RISK_PARITY_STRATEGY" in payload["series"]
    assert payload["series"]["h21052.CSI"][0]["date"] == "2021-01-04"
    assert payload["series"]["CN2296.CNI"][1]["value"] == 1050.0
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT_STRATEGY"][1]["value"] == 1.05
    assert payload["series"]["VIRTUAL_RISK_PARITY_STRATEGY"][1]["value"] == 1.05
    assert payload["background_series"][1]["value"] == 1050.0
