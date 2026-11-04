from __future__ import annotations

from myinvest_strategy_index.config import load_settings
from myinvest_strategy_index.value_compare import (
    CASHFLOW_GROWTH_COMPARE_INSTRUMENTS,
    CHINEXT_TOTAL_RETURN_INSTRUMENTS,
    DEFAULT_VALUE_COMPARE_INSTRUMENTS,
    FOUR_ASSET_CALMAR_INSTRUMENTS,
    THREE_ASSET_CALMAR_INSTRUMENTS,
    US_ETF_COMPARE_INSTRUMENTS,
    INFLATION_PORTFOLIO_INSTRUMENTS,
    US_ETF_OBSERVER_INSTRUMENTS,
    VALUE_COMPARE_BACKGROUND,
    get_cashflow_growth_compare_payload,
    get_chinext_total_return_payload,
    get_four_asset_calmar_payload,
    get_three_asset_calmar_payload,
    get_us_etf_compare_payload,
    get_inflation_portfolio_payload,
    get_us_etf_observer_payload,
    get_value_compare_payload,
)


def test_us_etf_payload_includes_six_funds_and_equal_weight_model(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {"RSP": 1100, "IWY": 1200, "MOAT": 1300, "SPMO": 1400, "PFF": 900, "VNQ": 1000}
    for instrument in US_ETF_COMPARE_INSTRUMENTS:
        if instrument.kind.startswith("synthetic_"):
            continue
        (settings.cache_dir / f"value_compare_{instrument.code}.csv").write_text(
            "date,close,value\n2021-01-04,1000,1000\n"
            f"2021-02-05,{second_values[instrument.code]},{second_values[instrument.code]}\n",
            encoding="utf-8",
        )

    payload = get_us_etf_compare_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert set(payload["series"]) == {"RSP", "IWY", "MOAT", "SPMO", "PFF", "VNQ", "VIRTUAL_US_ETF_EQUAL_WEIGHT"}
    assert payload["series"]["VIRTUAL_US_ETF_EQUAL_WEIGHT"][1]["value"] == 1.15
    assert payload["background"] is None


def test_inflation_portfolio_payload_uses_requested_fixed_weights(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {"SPMO": 1100, "MOAT": 1200, "IEF": 900, "IAU": 1050, "KMLM": 1150, "PDBC": 800}
    for instrument in INFLATION_PORTFOLIO_INSTRUMENTS:
        if instrument.kind.startswith("synthetic_"):
            continue
        (settings.cache_dir / f"value_compare_{instrument.code}.csv").write_text(
            "date,close,value\n2021-01-04,1000,1000\n"
            f"2021-02-05,{second_values[instrument.code]},{second_values[instrument.code]}\n",
            encoding="utf-8",
        )
    payload = get_inflation_portfolio_payload(settings)
    assert payload["ok"] is True
    assert not payload["errors"]
    assert set(payload["series"]) == {"SPMO", "MOAT", "IEF", "IAU", "KMLM", "PDBC", "VIRTUAL_INFLATION_PORTFOLIO", "VIRTUAL_INFLATION_EQUAL_WEIGHT"}
    assert payload["series"]["VIRTUAL_INFLATION_PORTFOLIO"][1]["value"] == 1.0625
    assert payload["series"]["VIRTUAL_INFLATION_EQUAL_WEIGHT"][1]["value"] == 1.033333


def test_us_etf_observer_payload_groups_29_funds_and_dynamic_equal_weight(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    real = [item for item in US_ETF_OBSERVER_INSTRUMENTS if not item.kind.startswith("synthetic_")]
    for index, instrument in enumerate(real):
        (settings.cache_dir / f"value_compare_{instrument.code}.csv").write_text(
            "date,close,value\n2021-01-04,1000,1000\n"
            f"2021-01-05,{1000 + index * 10},{1000 + index * 10}\n",
            encoding="utf-8",
        )
    payload = get_us_etf_observer_payload(settings)
    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(real) == 29
    codes = {item.code for item in real}
    assert "SPY" not in codes and "ITOT" not in codes
    assert {"RSP", "IWY", "MOAT", "SPMO", "PFF", "VNQ", "IEF", "IAU", "KMLM", "PDBC"} <= codes
    assert {item["category"] for item in payload["instruments"]} == {
        "核心 Beta", "风险/风格增强器", "防御或避险组件", "策略类", "组合对照"
    }
    assert "VIRTUAL_US_ETF_OBSERVER_EQUAL_WEIGHT" in payload["series"]
    assert len(payload["series"]) == 30


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
    assert "518880.SH" in payload["series"]
    assert "511260.SH" in payload["series"]
    assert "VIRTUAL_EQUAL_WEIGHT_STRATEGY" in payload["series"]
    assert "VIRTUAL_RISK_PARITY_STRATEGY" in payload["series"]
    assert "VIRTUAL_LAYERED_WEIGHT_STRATEGY" in payload["series"]
    assert payload["series"]["h21052.CSI"][0]["date"] == "2021-01-04"
    assert payload["series"]["CN2296.CNI"][1]["value"] == 1050.0
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT_STRATEGY"][1]["value"] == 1.05
    assert payload["series"]["VIRTUAL_RISK_PARITY_STRATEGY"][1]["value"] == 1.05
    assert payload["series"]["VIRTUAL_LAYERED_WEIGHT_STRATEGY"][1]["value"] == 1.05
    assert payload["background_series"][1]["value"] == 1050.0


def test_value_compare_synthetic_series_include_gold_and_bond_etfs(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    for instrument in [*DEFAULT_VALUE_COMPARE_INSTRUMENTS, VALUE_COMPARE_BACKGROUND]:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        second_value = 1200 if instrument.code in {"518880.SH", "511260.SH"} else 1000
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            f"2021-01-05,{second_value}.000,{second_value}.000\n",
            encoding="utf-8",
        )

    payload = get_value_compare_payload(settings)

    assert payload["ok"] is True
    assert payload["series"]["VIRTUAL_EQUAL_WEIGHT_STRATEGY"][1]["value"] == 1.066667
    assert payload["series"]["VIRTUAL_RISK_PARITY_STRATEGY"][1]["value"] == 1.066667
    assert payload["series"]["VIRTUAL_LAYERED_WEIGHT_STRATEGY"][1]["value"] == 1.127283


def test_layered_weight_model_uses_calmar_full_sample_weights(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {
        "CN2296.CNI": 1200,
        "480092.CNI": 1100,
        "h21052.CSI": 1050,
        "h20269.CSI": 900,
        "518880.SH": 1300,
        "511260.SH": 950,
    }
    for instrument in [*DEFAULT_VALUE_COMPARE_INSTRUMENTS, VALUE_COMPARE_BACKGROUND]:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        second_value = second_values.get(instrument.code, 1000)
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            f"2021-01-05,{second_value}.000,{second_value}.000\n",
            encoding="utf-8",
        )

    payload = get_value_compare_payload(settings)

    assert payload["ok"] is True
    assert payload["series"]["VIRTUAL_LAYERED_WEIGHT_STRATEGY"][1]["value"] == 1.098418


def test_value_compare_payload_includes_return_correlation_and_component_overlap(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    values = {
        "h21052.CSI": [100, 110, 132],
        "CN2296.CNI": [100, 120, 156],
        "h20269.CSI": [100, 90, 99],
        "480092.CNI": [100, 105, 115.5],
    }
    for instrument in [*DEFAULT_VALUE_COMPARE_INSTRUMENTS, VALUE_COMPARE_BACKGROUND]:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        series = values.get(instrument.code, [100, 101, 102])
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            f"2021-01-04,{series[0]},{series[0]}\n"
            f"2021-01-05,{series[1]},{series[1]}\n"
            f"2021-01-06,{series[2]},{series[2]}\n",
            encoding="utf-8",
        )
    constituents = {
        "h21052.CSI": "600001.SH,10\n600002.SH,20\n",
        "CN2296.CNI": "600002.SH,10\n600003.SH,20\n",
        "h20269.CSI": "600003.SH,10\n600004.SH,20\n",
        "480092.CNI": "600001.SH,15\n600003.SH,15\n",
    }
    for code, rows in constituents.items():
        safe_code = code.replace(".", "_")
        (settings.cache_dir / f"index_components_{safe_code}.csv").write_text(
            "con_code,trade_date,weight\n"
            + "".join(f"{row.split(',')[0]},2021-06-11,{row.split(',')[1]}" for row in rows.splitlines(True)),
            encoding="utf-8",
        )

    payload = get_value_compare_payload(settings)

    relationships = payload["index_relationships"]
    assert relationships["ok"] is True
    assert relationships["return_correlation"]["observations"] == 2
    assert relationships["return_correlation"]["matrix"]["h21052.CSI"]["CN2296.CNI"] == 1.0
    overlap = relationships["component_overlap"]
    assert overlap["ok"] is True
    assert overlap["matrix"]["h21052.CSI"]["CN2296.CNI"]["common_count"] == 1
    assert overlap["matrix"]["h21052.CSI"]["CN2296.CNI"]["union_count"] == 3
    assert overlap["matrix"]["h21052.CSI"]["CN2296.CNI"]["count_overlap"] == 0.333333
    assert overlap["matrix"]["h21052.CSI"]["CN2296.CNI"]["weight_overlap"] == 0.333333


def test_chinext_total_return_payload_reads_three_cached_indices(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {
        "399606.SZ": 1100,
        "CN2673.CNI": 1200,
        "CN2296.CNI": 1300,
    }
    for instrument in CHINEXT_TOTAL_RETURN_INSTRUMENTS:
        safe_code = instrument.code.replace(".", "_")
        second_value = second_values[instrument.code]
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            f"2021-01-05,{second_value}.000,{second_value}.000\n",
            encoding="utf-8",
        )

    payload = get_chinext_total_return_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == 3
    assert payload["background"] is None
    assert payload["background_series"] == []
    assert set(payload["series"]) == {"399606.SZ", "CN2673.CNI", "CN2296.CNI"}
    assert payload["series"]["399606.SZ"][1]["value"] == 1100.0
    assert payload["series"]["CN2673.CNI"][1]["value"] == 1200.0
    assert payload["series"]["CN2296.CNI"][1]["value"] == 1300.0


def test_cashflow_growth_payload_keeps_two_indices_and_same_virtual_features(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {
        "480092.CNI": 1200,
        "CN2296.CNI": 1100,
        "000001.SH": 1050,
    }
    for instrument in [*CASHFLOW_GROWTH_COMPARE_INSTRUMENTS, VALUE_COMPARE_BACKGROUND]:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        second_value = second_values[instrument.code]
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            f"2021-01-05,{second_value}.000,{second_value}.000\n",
            encoding="utf-8",
        )

    payload = get_cashflow_growth_compare_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == 6
    assert payload["background"]["code"] == "000001.SH"
    assert set(payload["series"]) == {
        "480092.CNI",
        "CN2296.CNI",
        "VIRTUAL_CASHFLOW_GROWTH_EQUAL_WEIGHT",
        "VIRTUAL_CASHFLOW_GROWTH_RISK_PARITY",
        "VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_RISK",
        "VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_REBALANCED_BEST",
    }
    assert payload["series"]["480092.CNI"][1]["value"] == 1200.0
    assert payload["series"]["CN2296.CNI"][1]["value"] == 1100.0
    assert payload["series"]["VIRTUAL_CASHFLOW_GROWTH_EQUAL_WEIGHT"][1]["value"] == 1.15
    assert payload["series"]["VIRTUAL_CASHFLOW_GROWTH_RISK_PARITY"][1]["value"] == 1.15
    assert payload["series"]["VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_RISK"][1]["value"] == 1.15
    assert payload["series"]["VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_REBALANCED_BEST"][1]["value"] == 1.15
    assert payload["rebalance_analysis"]["ok"] is True
    assert payload["rebalance_analysis"]["objective"] == "Calmar"
    assert payload["rebalance_analysis"]["best_rule_name"]
    candidate_ids = {item["id"] for item in payload["rebalance_analysis"]["candidates"]}
    assert {
        "none",
        "daily",
        "monthly",
        "quarterly",
        "semiannual",
        "annual",
        "threshold_5",
        "threshold_10",
        "threshold_15",
    } == candidate_ids
    drawdown_risk = next(
        item for item in payload["instruments"] if item["code"] == "VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_RISK"
    )
    assert drawdown_risk["name"] == "最大回撤风险平价组合"
    best_rebalanced = next(
        item
        for item in payload["instruments"]
        if item["code"] == "VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_REBALANCED_BEST"
    )
    assert best_rebalanced["name"] == "最大回撤风险平价最优再平衡组合"
    assert payload["background_series"][1]["value"] == 1050.0


def test_cashflow_growth_drawdown_risk_uses_inverse_max_drawdown_weights(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    values = {
        "480092.CNI": [1000, 650, 1000],
        "CN2296.CNI": [1000, 450, 1000],
        "000001.SH": [1000, 900, 1000],
    }
    for instrument in [*CASHFLOW_GROWTH_COMPARE_INSTRUMENTS, VALUE_COMPARE_BACKGROUND]:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        first, second, third = values[instrument.code]
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            f"2021-01-04,{first}.000,{first}.000\n"
            f"2021-01-05,{second}.000,{second}.000\n"
            f"2021-01-06,{third}.000,{third}.000\n",
            encoding="utf-8",
        )

    payload = get_cashflow_growth_compare_payload(settings)

    assert payload["ok"] is True
    drawdown_rows = payload["series"]["VIRTUAL_CASHFLOW_GROWTH_DRAWDOWN_RISK"]
    assert drawdown_rows[1]["value"] == 0.572222
    assert drawdown_rows[2]["value"] == 1.0325


def test_four_asset_calmar_payload_includes_equal_and_layered_models(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {
        "399606.SZ": 1100,
        "480092.CNI": 1200,
        "518880.SH": 1300,
        "511260.SH": 950,
    }
    for instrument in FOUR_ASSET_CALMAR_INSTRUMENTS:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        second_value = second_values[instrument.code]
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            f"2021-01-05,{second_value}.000,{second_value}.000\n",
            encoding="utf-8",
        )

    payload = get_four_asset_calmar_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == 6
    assert payload["background"] is None
    bond = next(item for item in payload["instruments"] if item["code"] == "511260.SH")
    assert bond["color"] == "#2563EB"
    assert set(payload["series"]) == {
        "399606.SZ",
        "480092.CNI",
        "518880.SH",
        "511260.SH",
        "VIRTUAL_FOUR_ASSET_EQUAL_WEIGHT",
        "VIRTUAL_FOUR_ASSET_CALMAR_LAYERED",
    }
    assert payload["series"]["VIRTUAL_FOUR_ASSET_EQUAL_WEIGHT"][1]["value"] == 1.1375
    assert payload["series"]["VIRTUAL_FOUR_ASSET_CALMAR_LAYERED"][1]["value"] == 1.109943


def test_three_asset_calmar_payload_includes_equal_and_layered_models(tmp_path) -> None:
    settings = load_settings(root=tmp_path, env_file=tmp_path / ".env")
    settings.cache_dir.mkdir(parents=True)
    second_values = {
        "399606.SZ": 1100,
        "480092.CNI": 1200,
        "518880.SH": 1300,
    }
    for instrument in THREE_ASSET_CALMAR_INSTRUMENTS:
        if instrument.kind.startswith("synthetic_"):
            continue
        safe_code = instrument.code.replace(".", "_")
        second_value = second_values[instrument.code]
        (settings.cache_dir / f"value_compare_{safe_code}.csv").write_text(
            "date,close,value\n"
            "2021-01-04,1000.000,1000.000\n"
            f"2021-01-05,{second_value}.000,{second_value}.000\n",
            encoding="utf-8",
        )

    payload = get_three_asset_calmar_payload(settings)

    assert payload["ok"] is True
    assert not payload["errors"]
    assert len(payload["instruments"]) == 5
    assert payload["background"] is None
    assert set(payload["series"]) == {
        "399606.SZ",
        "480092.CNI",
        "518880.SH",
        "VIRTUAL_THREE_ASSET_EQUAL_WEIGHT",
        "VIRTUAL_THREE_ASSET_CALMAR_LAYERED",
    }
    assert payload["series"]["VIRTUAL_THREE_ASSET_EQUAL_WEIGHT"][1]["value"] == 1.2
    assert payload["series"]["VIRTUAL_THREE_ASSET_CALMAR_LAYERED"][1]["value"] == 1.218319
