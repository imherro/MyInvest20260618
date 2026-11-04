from __future__ import annotations

from shortterm_trader.config import load_settings
from shortterm_trader.index_compare import DEFAULT_INDEX_INSTRUMENTS, get_index_compare_payload


def test_index_compare_payload_reads_cached_histories(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    for instrument in DEFAULT_INDEX_INSTRUMENTS:
        if instrument.kind == "synthetic_equal_weight":
            continue
        safe_code = instrument.code.replace(".", "_")
        (settings.cache_dir / f"index_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            "2021-01-05,1050.000,1050.000\n",
            encoding="utf-8",
        )

    payload = get_index_compare_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == len(DEFAULT_INDEX_INSTRUMENTS)
    assert "VIRTUAL_EQUAL_WEIGHT_INDEX" in payload["series"]
    assert payload["series"]["h20269.CSI"][0]["date"] == "2021-01-04"
    assert payload["series"]["h20269.CSI"][1]["value"] == 1050.0
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT_INDEX"][0]["value"] == 1.0
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT_INDEX"][1]["value"] == 1.05
