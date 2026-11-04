from __future__ import annotations

import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


POSITION_COLUMN_ALIASES = {
    "symbol": ["symbol", "证券代码", "股票代码", "代码", "证券编号", "stock_code"],
    "name": ["name", "证券名称", "股票名称", "名称", "stock_name"],
    "quantity": ["quantity", "持仓数量", "持仓", "股票余额", "证券数量", "数量", "当前持仓", "current_amount"],
    "available_quantity": ["available_quantity", "可用数量", "可用余额", "可卖数量", "可卖", "enable_amount"],
    "last_price": ["last_price", "最新价", "当前价", "现价", "参考价", "市价", "price"],
    "market_value": ["market_value", "市值", "持仓市值", "参考市值", "证券市值", "市值金额"],
    "cost_price": ["cost_price", "成本价", "持仓成本价", "成本", "参考成本价"],
    "profit_loss": ["profit_loss", "浮动盈亏", "盈亏", "持仓盈亏", "参考盈亏"],
    "profit_loss_pct": ["profit_loss_pct", "盈亏比例", "盈亏比例(%)", "盈亏率", "收益率", "profit_rate"],
    "position_pct": ["position_pct", "持仓占比", "仓位占比", "占比"],
}

POSITION_OUTPUT_COLUMNS = [
    "symbol",
    "name",
    "quantity",
    "available_quantity",
    "last_price",
    "market_value",
    "cost_price",
    "profit_loss",
    "profit_loss_pct",
    "position_pct",
]


class QmtUnavailable(RuntimeError):
    pass


@dataclass
class QmtProvider:
    """Optional read-only QMT adapter.

    The installed XtQuant SDK is usually tied to Python 3.11 on this machine.
    Keep this adapter isolated so the rest of the system still runs on newer
    Python runtimes.
    """

    sdk_path: Path | None = None

    def available(self) -> bool:
        try:
            self._import_xtdata()
        except Exception:
            return False
        return True

    def get_full_ticks(self, symbols: list[str]) -> dict[str, dict[str, object]]:
        try:
            xtdata = self._import_xtdata()
        except Exception as exc:
            raise QmtUnavailable(f"xtquant import failed: {exc}") from exc
        return xtdata.get_full_tick(symbols)

    def probe(self, symbols: list[str] | None = None) -> dict[str, object]:
        checked_at = datetime.now().isoformat(timespec="seconds")
        status: dict[str, object] = {
            "checked_at": checked_at,
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "sdk_path": str(self.sdk_path) if self.sdk_path else None,
            "xtquant_importable": False,
            "terminal_connected": False,
            "symbols_checked": symbols or [],
            "message": "",
        }
        try:
            xtdata = self._import_xtdata()
            status["xtquant_importable"] = True
        except Exception as exc:
            status["message"] = f"xtquant import failed: {exc}"
            return status

        if not symbols:
            status["message"] = "xtquant importable; no realtime symbols checked"
            return status
        try:
            ticks = xtdata.get_full_tick(symbols)
            status["terminal_connected"] = bool(ticks)
            status["tick_count"] = len(ticks) if isinstance(ticks, dict) else 0
            status["message"] = "tick data returned" if ticks else "xtquant imported but no tick data returned"
        except Exception as exc:
            status["message"] = f"tick probe failed: {exc}"
        return status

    def snapshot(self, symbols: list[str]) -> dict[str, object]:
        ticks = self.get_full_ticks(symbols)
        return {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "symbols": symbols,
            "ticks": _jsonable(ticks),
        }

    def _import_xtdata(self) -> Any:
        _prepare_sdk_path(self.sdk_path)
        from xtquant import xtdata

        return xtdata


def write_realtime_snapshot(path: Path, provider: QmtProvider, symbols: list[str]) -> dict[str, object]:
    payload = provider.snapshot(symbols)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def read_realtime_snapshot(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def watch_realtime_snapshot(
    path: Path,
    provider: QmtProvider,
    symbols: list[str],
    interval: float,
    iterations: int | None = None,
) -> None:
    count = 0
    while iterations is None or count < iterations:
        payload = write_realtime_snapshot(path, provider, symbols)
        print(json.dumps({"updated_at": payload["updated_at"], "symbols": symbols}, ensure_ascii=False), flush=True)
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(interval)


def load_position_export(path: Path) -> pd.DataFrame:
    """Read a user-exported QMT holdings CSV/XLSX file without mutation."""
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    else:
        frame = _read_position_csv(path)
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def normalize_position_export(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    aliases = {_column_key(alias): canonical for canonical, values in POSITION_COLUMN_ALIASES.items() for alias in values}
    source_columns = {_column_key(column): column for column in frame.columns}
    for canonical in POSITION_OUTPUT_COLUMNS:
        source = next(
            (source_columns[_column_key(alias)] for alias in POSITION_COLUMN_ALIASES[canonical] if _column_key(alias) in source_columns),
            None,
        )
        out[canonical] = frame[source] if source is not None else pd.NA

    out["symbol"] = out["symbol"].map(_normalize_position_symbol)
    out = out[out["symbol"].astype(str).str.len() > 0].copy()
    for column in [
        "quantity",
        "available_quantity",
        "last_price",
        "market_value",
        "cost_price",
        "profit_loss",
        "profit_loss_pct",
        "position_pct",
    ]:
        out[column] = out[column].map(_number_or_none)
    out["name"] = out["name"].fillna("").astype(str).str.strip()
    return out.reset_index(drop=True)


def import_position_export(source_path: Path, snapshot_path: Path, csv_path: Path) -> dict[str, object]:
    raw = load_position_export(source_path)
    normalized = normalize_position_export(raw)
    return write_position_snapshot(
        normalized,
        snapshot_path,
        csv_path,
        source_file=source_path.name,
        source_type="export_file",
        raw_columns=[str(column) for column in raw.columns],
    )


def import_terminal_positions(
    *,
    sdk_path: Path | None,
    userdata_path: Path | None,
    account_id: str | None,
    snapshot_path: Path,
    csv_path: Path,
) -> dict[str, object]:
    resolved_userdata = resolve_qmt_userdata_path(userdata_path, sdk_path)
    if resolved_userdata is None:
        raise QmtUnavailable("QMT userdata path was not found. Configure QMT_USERDATA_PATH.")
    resolved_account = resolve_qmt_account_id(account_id, resolved_userdata)
    if resolved_account is None:
        raise QmtUnavailable("QMT account id was not found. Configure QMT_ACCOUNT_ID.")
    positions, asset = query_terminal_positions(sdk_path, resolved_userdata, resolved_account)
    symbols = [_normalize_position_symbol(getattr(position, "stock_code", "")) for position in positions]
    names = query_instrument_names(sdk_path, symbols)
    frame = normalize_terminal_positions(positions, asset, names)
    return write_position_snapshot(
        frame,
        snapshot_path,
        csv_path,
        source_file="QMT terminal",
        source_type="qmt_terminal",
        account_id=_mask_account_id(resolved_account),
        raw_columns=POSITION_OUTPUT_COLUMNS,
    )


def query_terminal_positions(
    sdk_path: Path | None,
    userdata_path: Path,
    account_id: str,
) -> tuple[list[object], object | None]:
    _prepare_sdk_path(sdk_path)
    try:
        from xtquant.xttrader import XtQuantTrader
        from xtquant.xttype import StockAccount
    except Exception as exc:
        raise QmtUnavailable(f"xtquant trader import failed: {exc}") from exc

    trader = XtQuantTrader(str(userdata_path), random.randint(100000, 999999999))
    try:
        trader.start()
        result = trader.connect()
        if result != 0:
            raise QmtUnavailable(f"QMT trader connect failed: {result}")
        account = StockAccount(account_id)
        subscribe_result = trader.subscribe(account)
        if subscribe_result != 0:
            raise QmtUnavailable(f"QMT account subscribe failed: {subscribe_result}")
        asset = trader.query_stock_asset(account)
        positions = trader.query_stock_positions(account) or []
        return list(positions), asset
    finally:
        try:
            trader.stop()
        except Exception:
            pass


def query_instrument_names(sdk_path: Path | None, symbols: list[str]) -> dict[str, str]:
    _prepare_sdk_path(sdk_path)
    try:
        from xtquant import xtdata
    except Exception:
        return {}
    names: dict[str, str] = {}
    for symbol in dict.fromkeys(symbol for symbol in symbols if symbol):
        try:
            detail = xtdata.get_instrument_detail(symbol) or {}
        except Exception:
            continue
        name = str(detail.get("InstrumentName") or "").strip()
        if name:
            names[symbol] = name
    return names


def normalize_terminal_positions(
    positions: list[object],
    asset: object | None = None,
    names: dict[str, str] | None = None,
) -> pd.DataFrame:
    total_asset = _number_or_none(getattr(asset, "total_asset", None)) if asset is not None else None
    names = names or {}
    rows: list[dict[str, object]] = []
    for position in positions:
        symbol = _normalize_position_symbol(getattr(position, "stock_code", ""))
        quantity = _number_or_none(getattr(position, "volume", None))
        market_value = _number_or_none(getattr(position, "market_value", None))
        last_price = None
        if quantity and market_value is not None:
            last_price = market_value / quantity
        position_pct = None
        if total_asset and market_value is not None:
            position_pct = market_value / total_asset
        rows.append(
            {
                "symbol": symbol,
                "name": names.get(symbol, ""),
                "quantity": quantity,
                "available_quantity": _number_or_none(getattr(position, "can_use_volume", None)),
                "last_price": last_price,
                "market_value": market_value,
                "cost_price": _number_or_none(getattr(position, "open_price", None)),
                "profit_loss": None,
                "profit_loss_pct": None,
                "position_pct": position_pct,
            }
        )
    frame = pd.DataFrame(rows, columns=POSITION_OUTPUT_COLUMNS)
    if frame.empty:
        return frame
    frame = frame[frame["symbol"].astype(str).str.len() > 0].copy()
    return frame.reset_index(drop=True)


def write_position_snapshot(
    frame: pd.DataFrame,
    snapshot_path: Path,
    csv_path: Path,
    *,
    source_file: str,
    source_type: str,
    raw_columns: list[str] | None = None,
    account_id: str | None = None,
) -> dict[str, object]:
    normalized = frame.reindex(columns=POSITION_OUTPUT_COLUMNS)
    imported_at = datetime.now().isoformat(timespec="seconds")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload: dict[str, object] = {
        "imported_at": imported_at,
        "source_file": source_file,
        "source_type": source_type,
        "rows": int(len(normalized)),
        "raw_columns": raw_columns or [],
        "csv": csv_path.name,
        "positions": _jsonable(normalized.to_dict("records")),
    }
    if account_id:
        payload["account_id"] = account_id
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def read_position_snapshot(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def resolve_qmt_userdata_path(configured: Path | None, sdk_path: Path | None) -> Path | None:
    candidates: list[Path] = []
    if configured is not None:
        candidates.append(configured)
    if sdk_path is not None:
        base = sdk_path if sdk_path.is_dir() else sdk_path.parent
        for parent in [base, *base.parents]:
            candidates.extend([parent / "userdata_mini", parent / "userdata"])
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and (resolved / "users").exists():
            return resolved
    return None


def resolve_qmt_account_id(configured: str | None, userdata_path: Path) -> str | None:
    if configured:
        return configured.strip()
    users_dir = userdata_path / "users"
    if not users_dir.exists():
        return None
    account_dirs = sorted(
        path.name for path in users_dir.iterdir() if path.is_dir() and path.name.isdigit()
    )
    if len(account_dirs) == 1:
        return account_dirs[0]
    return None


def _prepare_sdk_path(sdk_path: Path | None) -> None:
    if sdk_path is None:
        return
    if not sdk_path.exists():
        raise FileNotFoundError(f"QMT_SDK_PATH does not exist: {sdk_path}")
    import_path = sdk_path.parent if sdk_path.name.lower() == "xtquant" else sdk_path
    text = str(import_path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _read_position_csv(path: Path) -> pd.DataFrame:
    errors: list[Exception] = []
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            errors.append(exc)
    raise errors[-1]


def _column_key(value: object) -> str:
    return re.sub(r"[\s_（）()%()]+", "", str(value).strip().lower())


def _normalize_position_symbol(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)) and float(value).is_integer():
        text = f"{int(value):06d}"
    else:
        text = str(value).strip().upper()
    text = text.replace("SH.", "").replace("SZ.", "").replace("BJ.", "") if re.match(r"^(SH|SZ|BJ)\.\d{6}$", text) else text
    if re.match(r"^\d{6}\.(SH|SZ|BJ)$", text):
        return text
    if re.match(r"^(SH|SZ|BJ)\d{6}$", text):
        return f"{text[2:]}.{text[:2]}"
    digits = re.sub(r"\D", "", text)
    if len(digits) == 6:
        if digits.startswith(("6", "9")):
            return f"{digits}.SH"
        if digits.startswith(("0", "3")):
            return f"{digits}.SZ"
        if digits.startswith(("4", "8")):
            return f"{digits}.BJ"
    return text


def _mask_account_id(account_id: str) -> str:
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]


def _number_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"--", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
