# TASK 1 Result

TASK 1 implements the TenBagger data layer and stock universe construction.

## Implemented

- `TenBaggerDataLoader` with TuShare primary ingestion.
- Multi-source interface stubs for BaoStock, QMT positions, and yfinance.
- Standard dataframe schema:
  `ts_code`, `date`, `open`, `high`, `low`, `close`, `revenue`,
  `net_profit`, `roe`, `pe`, `pb`, `market_cap`.
- Per-stock parquet files under local `data/parquet/by_stock/`.
- Date-partitioned parquet dataset under local `data/parquet/by_date/`.
- TASK 1 report generation under local `reports/`.
- FastAPI web dashboard served on port `8020`.
- Unit tests for schema, parquet storage, and report generation.
- Extended financial fields for later filters, including `debt_ratio`.

## Validation Run

Command:

```powershell
python scripts/run_task1.py --limit 10 --start-date 20230101
```

Result:

```json
{
  "stock_count": 10,
  "row_count": 8390,
  "date_range": {
    "start": "2023-01-03",
    "end": "2026-06-24"
  },
  "latest_trading_date": "2026-06-24",
  "missing_rates": {
    "ts_code": 0.0,
    "date": 0.0,
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0,
    "revenue": 0.0,
    "net_profit": 0.0,
    "roe": 0.0,
    "pe": 0.0,
    "pb": 0.0,
    "market_cap": 0.0
  },
  "loaded_codes": [
    "000001.SZ",
    "000651.SZ",
    "000858.SZ",
    "002415.SZ",
    "002594.SZ",
    "300750.SZ",
    "600000.SH",
    "600519.SH",
    "600887.SH",
    "601318.SH"
  ]
}
```

Test command:

```powershell
python -m pytest -q
```

Result:

```text
2 passed
```

Web command:

```powershell
python scripts/serve_web.py --port 8020
```

URL:

```text
http://127.0.0.1:8020
```
