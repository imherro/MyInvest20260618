from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tenbagger.config import DEFAULT_UNIVERSE
from tenbagger.data_loader import DEFAULT_REQUEST_INTERVAL_SECONDS, TenBaggerDataLoader
from tenbagger.universe import UniverseManager, filter_frame_to_universe
from tenbagger.universe.provider import StaticUniverseProvider


def _stock_basic(count: int = 650) -> pd.DataFrame:
    rows = []
    for idx in range(1, count + 1):
        exchange = "SZ" if idx % 2 else "SH"
        rows.append(
            {
                "ts_code": f"{idx:06d}.{exchange}",
                "symbol": f"{idx:06d}",
                "name": f"公司{idx:06d}",
                "area": "CN",
                "industry": "测试",
                "list_date": "20100101",
            }
        )
    rows.extend(
        [
            {"ts_code": "900001.SH", "name": "ST测试", "list_date": "20100101"},
            {"ts_code": "900002.SH", "name": "退市测试", "list_date": "20100101"},
        ]
    )
    return pd.DataFrame(rows)


def test_research_universe_is_filtered_and_large_enough() -> None:
    provider = StaticUniverseProvider(_stock_basic())

    details = UniverseManager.get_details("research", provider=provider)

    assert details["stock_count"] == 500
    assert 300 <= details["stock_count"] <= 1000
    assert "900001.SH" not in details["codes"]
    assert "900002.SH" not in details["codes"]
    assert details["filter_stats"]["raw"] == 652
    assert details["filter_stats"]["eligible"] == 650


def test_dev_universe_uses_fifty_codes_when_available() -> None:
    provider = StaticUniverseProvider(_stock_basic())

    codes = UniverseManager.get("dev", provider=provider)

    assert len(codes) == 50
    assert codes[0] == "000001.SZ"


def test_config_default_universe_is_not_research_source() -> None:
    assert DEFAULT_UNIVERSE == "DEV_ONLY"


def test_data_loader_requires_explicit_universe() -> None:
    loader = TenBaggerDataLoader(token="test-token")

    assert loader.request_interval == DEFAULT_REQUEST_INTERVAL_SECONDS
    assert loader._normalize_universe(["603259.sh", "603259.SH", ""]) == ["603259.SH"]
    with pytest.raises(ValueError, match="explicit non-empty universe"):
        loader._normalize_universe([])


def test_filter_frame_to_universe_restricts_local_task_data() -> None:
    frame = pd.DataFrame({"ts_code": ["000001.SZ", "600519.SH"], "value": [1, 2]})

    filtered = filter_frame_to_universe(frame, ["600519.SH"])

    assert filtered["ts_code"].tolist() == ["600519.SH"]


def test_task1_cli_no_longer_exposes_limit() -> None:
    script = Path("scripts/run_task1.py").read_text(encoding="utf-8")

    assert ("--" + "limit") not in script
    assert "--universe" in script
    assert "--request-interval" in script
