from types import SimpleNamespace

import pandas as pd

from shortterm_trader.data.qmt import (
    import_position_export,
    normalize_position_export,
    normalize_terminal_positions,
    read_position_snapshot,
    read_realtime_snapshot,
    resolve_qmt_account_id,
)


def test_read_realtime_snapshot_handles_missing_file(tmp_path) -> None:
    assert read_realtime_snapshot(tmp_path / "missing.json") is None


def test_read_realtime_snapshot_handles_invalid_json(tmp_path) -> None:
    path = tmp_path / "qmt_realtime.json"
    path.write_text("{broken", encoding="utf-8")
    assert read_realtime_snapshot(path) is None


def test_normalize_position_export_maps_chinese_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "证券代码": "000001",
                "证券名称": "平安银行",
                "持仓数量": "1000",
                "可用数量": "800",
                "最新价": "10.5",
                "持仓市值": "10500",
                "成本价": "9.8",
                "浮动盈亏": "700",
                "盈亏比例(%)": "7.14",
            }
        ]
    )
    normalized = normalize_position_export(frame)
    row = normalized.iloc[0]
    assert row["symbol"] == "000001.SZ"
    assert row["name"] == "平安银行"
    assert row["quantity"] == 1000.0
    assert row["profit_loss_pct"] == 7.14


def test_import_position_export_writes_snapshot_and_csv(tmp_path) -> None:
    source = tmp_path / "positions.csv"
    source.write_text("证券代码,证券名称,持仓数量,持仓市值\n600519,贵州茅台,100,150000\n", encoding="utf-8-sig")
    snapshot = tmp_path / "qmt_positions_latest.json"
    csv_path = tmp_path / "qmt_positions_latest.csv"

    payload = import_position_export(source, snapshot, csv_path)
    stored = read_position_snapshot(snapshot)

    assert payload["rows"] == 1
    assert stored is not None
    assert stored["positions"][0]["symbol"] == "600519.SH"
    assert csv_path.exists()


def test_normalize_terminal_positions_maps_qmt_objects() -> None:
    positions = [
        SimpleNamespace(
            stock_code="600519.SH",
            volume=100,
            can_use_volume=80,
            open_price=1500,
            market_value=160000,
        )
    ]
    asset = SimpleNamespace(total_asset=800000)

    frame = normalize_terminal_positions(positions, asset, {"600519.SH": "贵州茅台"})
    row = frame.iloc[0]

    assert row["symbol"] == "600519.SH"
    assert row["name"] == "贵州茅台"
    assert row["quantity"] == 100
    assert row["available_quantity"] == 80
    assert row["last_price"] == 1600
    assert row["position_pct"] == 0.2


def test_resolve_qmt_account_id_autodetects_single_account(tmp_path) -> None:
    users = tmp_path / "users"
    (users / "12345678").mkdir(parents=True)

    assert resolve_qmt_account_id(None, tmp_path) == "12345678"
