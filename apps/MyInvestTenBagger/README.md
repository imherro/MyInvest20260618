# TenBagger

TenBagger is a local A-share research system for building a verifiable
structural tenbagger screening pipeline.

Current milestones:

- TASK 1: data layer and stock universe construction.
- TASK 2: factor engine and cross-sectional structural scores.
- TASK 3: hard-filter screener and alpha validation.
- TASK 4: portfolio simulation backtest.
- TASK 5: factor neutralization and walk-forward weight optimization.
- TASK 6: alpha monetization and execution optimization.
- TASK 7: structural alpha validation and final alpha classification.
- TASK 8: market regime and behavioral state engine.
- TASK 9: market behavior and flow pressure engine.
- TASK 10: market structure decomposition engine.
- TASK 11: market structural anomaly detection engine.

## TASK 1 Scope

- Unified `TenBaggerDataLoader` interface.
- TuShare primary data ingestion for stock basics, daily bars, daily valuation,
  income, cash flow, and ROE data.
- Placeholder multi-source methods for BaoStock, QMT positions, and yfinance.
- Standard dataframe schema:
  `ts_code`, `date`, `open`, `high`, `low`, `close`, `revenue`, `net_profit`,
  `roe`, `pe`, `pb`, `market_cap`.
- Parquet storage by stock and by date partition.
- Local task report with stock count, coverage, missing-rate stats, and latest
  trading snapshot.
- Web display on port `8020`.

## Setup

Create a local `.env` file with:

```text
TUSHARE_TOKEN=your_token
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run TASK 1

```powershell
python scripts/run_task1.py --universe dev --start-date 20230101
```

Generated parquet files are written under `data/parquet/` and reports under
`reports/`. Both folders are local runtime outputs and are not committed.
TASK 1 waits between per-stock TuShare request batches. The default interval is
`0.4` seconds, and can be adjusted with:

```powershell
python scripts/run_task1.py --universe research --request-interval 0.5
```

## Universe Selection

All task scripts accept the same universe switch:

```powershell
python scripts/run_universe.py --level research
python scripts/run_task1.py --universe research
python scripts/run_task2.py --universe research
```

Supported levels are:

- `dev`: 50-stock development universe.
- `research`: filtered research universe, normally 300 to 1000 stocks.
- `production`: full filtered A-share universe.

`tenbagger.universe.UniverseManager` is the single entry point for stock
universe construction. `tenbagger.config.DEFAULT_UNIVERSE` is only a legacy
`DEV_ONLY` marker and is not used for research selection.

## Web Display

```powershell
python scripts/serve_web.py --port 8020
```

Then open:

```text
http://127.0.0.1:8020
```

The dashboard reads local TASK 1 and TASK 2 reports when they exist.

## API Catalog

The local web service exposes a read-only interface catalog:

```text
GET /api
```

`/api` returns JSON describing all public routes in the current system. The
response includes:

- system name, version, description, and `base_url`
- documentation links: `/docs`, `/redoc`, `/openapi.json`
- recommended entrypoints
- safety boundaries
- grouped endpoints
- `total_endpoints`

Each endpoint entry includes `method`, `path`, purpose, parameters, return
content, and whether it is read-only. The catalog itself is documentation only:
it does not trigger recomputation, local writes, trading, synchronization, or
external side effects.

Recommended starting points:

- `/api`: endpoint discovery and safety notes.
- `/`: default Model V2 dashboard.
- `/api/task3`: Model V2 candidate and validation summary.
- `/api/task8/regime`: current market regime.
- `/api/task9/behavior`: current behavioral flow state.
- `/api/task10/structure`: current market structure state.
- `/api/task11/anomaly`: current structural anomaly state.

Safety note: most API endpoints read existing local reports only. The catalog
flags `/api/universe/revaluation` as non-read-only because that endpoint may
write a local revaluation report.

## Run TASK 2

Run TASK 1 first, then:

```powershell
python scripts/run_task2.py
```

TASK 2 writes factor parquet files under `data/factors/` and the factor report
under `reports/task2_factor_summary.json`.

TASK 2 also writes the parallel Model V2 scoring layer. V2 keeps the original
`tenbagger_score` intact and adds `tenbagger_score_v2`, hard-gate eligibility,
dynamic weight profile, and A/B/C/D confidence grades. See
`docs/MODEL_V2_RESULT.md`.

## Run TASK 3

Run TASK 1 and TASK 2 first, then:

```powershell
python scripts/run_task3.py
```

TASK 3 writes screener parquet files under `data/screener/` and the screener
report under `reports/task3_screener_summary.json`.

## Run TASK 4

Run TASK 1 through TASK 3 first, then:

```powershell
python scripts/run_task4.py --top-k 10 --weight-mode score
```

TASK 4 writes portfolio NAV, holdings, and factor attribution parquet files
under `data/backtest/` and the backtest report under
`reports/task4_backtest_summary.json`.

## Run TASK 5

Run TASK 1 through TASK 4 first, then:

```powershell
python scripts/run_task5.py
```

TASK 5 writes the optimization report under
`reports/task5_optimization_summary.json`.

## Run TASK 6

Run TASK 1 through TASK 5 first, then:

```powershell
python scripts/run_task6.py
```

TASK 6 writes the monetization report under
`reports/task6_monetization_summary.json`.

## Run TASK 7

Run TASK 1 through TASK 6 first, then:

```powershell
python scripts/run_task7.py
```

TASK 7 writes the structural alpha validation report under
`reports/task7_structural_validation_summary.json`. The output classifies the
system as `REAL`, `PSEUDO`, or `NO ALPHA`.

## Run TASK 8

Run TASK 1 first so local market data exists, then:

```powershell
python scripts/run_task8.py
```

TASK 8 writes market regime reports under `reports/` and daily regime data under
`data/regime/`. It adds `GET /api/task8/regime` and a Market Regime Dashboard on
the local web display.

## Run TASK 9

Run TASK 8 first, then:

```powershell
python scripts/run_task9.py
```

TASK 9 writes behavioral flow reports under `reports/` and daily behavior data
under `data/behavior/`. It adds `GET /api/task9/behavior` and a Behavioral Flow
Dashboard on the local web display.

## Run TASK 10

Run TASK 9 first, then:

```powershell
python scripts/run_task10.py
```

TASK 10 writes market structure reports under `reports/` and daily structure
data under `data/structure/`. It adds `GET /api/task10/structure` and a Market
Structure Dashboard on the local web display.

## Run TASK 11

Run TASK 10 first, then:

```powershell
python scripts/run_task11.py
```

TASK 11 writes anomaly reports under `reports/` and daily anomaly data under
`data/anomaly/`. It adds `GET /api/task11/anomaly` and a Structural Anomaly
Dashboard on the local web display.

## Run TASK U2 Re-evaluation

After generating task reports for at least two universe levels, compare them:

```powershell
python scripts/run_universe_revaluation.py --baseline dev --target research
```

The re-evaluation reads existing reports only. It does not optimize weights,
change factor definitions, or tune alpha. It writes:

- `reports/universe_revaluation_summary.json`
- `reports/TASK_U2_REEVALUATION.md`
- `GET /api/universe/revaluation`

## Tests

```powershell
python -m pytest -q
```
