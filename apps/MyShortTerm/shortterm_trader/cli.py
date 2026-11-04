from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from importlib.util import find_spec
from pathlib import Path

import pandas as pd

from shortterm_trader.backtest import run_backtest
from shortterm_trader.config import ensure_runtime_dirs, load_settings, redacted_source_status
from shortterm_trader.data.qmt import (
    QmtProvider,
    QmtUnavailable,
    import_position_export,
    import_terminal_positions,
    load_position_export,
    read_realtime_snapshot,
    watch_realtime_snapshot,
    write_realtime_snapshot,
)
from shortterm_trader.data.router import MarketDataRouter
from shortterm_trader.data.store import SQLiteDataStore
from shortterm_trader.intraday import (
    append_intraday_alerts,
    build_intraday_monitor,
    latest_plan_path,
    load_plan,
    write_intraday_reports,
    write_intraday_status,
)
from shortterm_trader.planning import build_next_day_plan, write_plan_reports
from shortterm_trader.strategy.short_term import latest_signal
from shortterm_trader.symbols import normalize_symbol
from shortterm_trader.universe import load_universe


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()
    ensure_runtime_dirs(settings)
    router = MarketDataRouter(settings)
    return args.func(args, settings, router)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shortterm", description="Short-term trading research system")
    sub = parser.add_subparsers(required=True)

    doctor = sub.add_parser("doctor", help="Check local configuration and optional data-source packages")
    doctor.set_defaults(func=_doctor)

    fetch = sub.add_parser("fetch", help="Fetch daily bars for one symbol")
    fetch.add_argument("symbol")
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.set_defaults(func=_fetch)

    sync = sub.add_parser("sync-bars", help="Fetch a universe and persist daily bars into the local data store")
    sync.add_argument("--universe", default="config/universe.sample.csv")
    sync.add_argument("--start", required=True)
    sync.add_argument("--end", required=True)
    sync.set_defaults(func=_sync_bars)

    scan = sub.add_parser("scan", help="Scan a universe and write candidate reports")
    scan.add_argument("--universe", default="config/universe.sample.csv")
    scan.add_argument("--start", required=True)
    scan.add_argument("--end", required=True)
    scan.set_defaults(func=_scan)

    plan = sub.add_parser("plan", help="Generate a next-day short-term trading research plan")
    plan.add_argument("--universe", default="config/universe.sample.csv")
    plan.add_argument("--start", required=True)
    plan.add_argument("--end", required=True)
    plan.set_defaults(func=_plan)

    backtest = sub.add_parser("backtest", help="Backtest the short-term signal for one symbol")
    backtest.add_argument("symbol")
    backtest.add_argument("--start", required=True)
    backtest.add_argument("--end", required=True)
    backtest.set_defaults(func=_backtest)

    macro = sub.add_parser("macro", help="Fetch a FRED macro series")
    macro.add_argument("series_id")
    macro.add_argument("--start")
    macro.add_argument("--end")
    macro.set_defaults(func=_macro)

    qmt = sub.add_parser("qmt-positions", help="Load read-only QMT positions from terminal or export")
    qmt.add_argument("--file")
    qmt.set_defaults(func=_qmt_positions)

    qmt_doctor = sub.add_parser("qmt-doctor", help="Check read-only QMT realtime SDK availability")
    qmt_doctor.add_argument("--symbols", help="Comma-separated symbols to probe, for example 000001.SZ,510300.SH")
    qmt_doctor.set_defaults(func=_qmt_doctor)

    qmt_snapshot = sub.add_parser("qmt-snapshot", help="Fetch one read-only QMT realtime tick snapshot")
    qmt_snapshot.add_argument("--symbols", help="Comma-separated symbols; defaults to QMT_REALTIME_SYMBOLS")
    qmt_snapshot.set_defaults(func=_qmt_snapshot)

    qmt_watch = sub.add_parser("qmt-watch", help="Continuously refresh read-only QMT realtime ticks")
    qmt_watch.add_argument("--symbols", help="Comma-separated symbols; defaults to QMT_REALTIME_SYMBOLS")
    qmt_watch.add_argument("--interval", type=float, default=3.0)
    qmt_watch.add_argument("--iterations", type=int)
    qmt_watch.set_defaults(func=_qmt_watch)

    intraday = sub.add_parser("intraday-monitor", help="Evaluate latest plan against QMT realtime snapshot")
    intraday.add_argument("--plan", help="Plan CSV path; defaults to latest reports/plan_*.csv")
    intraday.add_argument("--no-alerts", action="store_true", help="Skip alert log writes")
    intraday.set_defaults(func=_intraday_monitor)

    intraday_watch = sub.add_parser("intraday-watch", help="Continuously evaluate latest plan against QMT realtime snapshot")
    intraday_watch.add_argument("--plan", help="Plan CSV path; defaults to latest reports/plan_*.csv each cycle")
    intraday_watch.add_argument("--interval", type=float, default=3.0)
    intraday_watch.add_argument("--iterations", type=int)
    intraday_watch.add_argument("--write-reports", action="store_true", help="Also write intraday_*.csv/md each cycle")
    intraday_watch.add_argument("--no-alerts", action="store_true", help="Skip alert log writes")
    intraday_watch.set_defaults(func=_intraday_watch)
    return parser


def _doctor(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    modules = ["pandas", "numpy", "requests", "tushare", "baostock", "yfinance", "fredapi", "dotenv", "xtquant"]
    status = {
        "root": str(settings.root),
        "sources": redacted_source_status(settings),
        "modules": {module: bool(find_spec(module)) for module in modules},
        "qmt_xtdata_available": QmtProvider(settings.qmt_sdk_path).available(),
    }
    store = SQLiteDataStore(settings.db_path)
    coverage = store.coverage(limit=5)
    status["data_store"] = {
        "path": str(settings.db_path),
        "symbols": int(len(coverage)),
        "latest": coverage.to_dict("records"),
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def _fetch(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    bars = router.get_daily_bars(args.symbol, args.start, args.end)
    SQLiteDataStore(settings.db_path).upsert_daily_bars(bars)
    output = settings.cache_dir / f"{args.symbol.replace('.', '_')}_{args.start}_{args.end}.csv"
    bars.to_csv(output, index=False, encoding="utf-8")
    print(f"rows={len(bars)} output={output}")
    return 0


def _sync_bars(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    universe = load_universe(args.universe)
    store = SQLiteDataStore(settings.db_path)
    rows = 0
    errors: list[dict[str, str]] = []
    for item in universe:
        symbol = normalize_symbol(str(item["symbol"]))
        try:
            bars = router.get_daily_bars(symbol, args.start, args.end)
            rows += store.upsert_daily_bars(bars)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
    print(json.dumps({"symbols": len(universe), "rows": rows, "errors": errors, "db": str(settings.db_path)}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def _scan(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    universe = load_universe(args.universe)
    store = SQLiteDataStore(settings.db_path)
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for item in universe:
        symbol = normalize_symbol(str(item["symbol"]))
        try:
            bars = router.get_daily_bars(symbol, args.start, args.end)
            store.upsert_daily_bars(bars)
            signal = latest_signal(bars)
            signal["name"] = item.get("name", "")
            rows.append(signal)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["signal", "score"], ascending=[False, False])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = settings.reports_dir / f"scan_{stamp}.csv"
    md_path = settings.reports_dir / f"scan_{stamp}.md"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    _write_scan_markdown(md_path, result, errors)
    print(f"candidates={len(result)} errors={len(errors)} csv={csv_path} markdown={md_path}")
    return 0 if rows else 2


def _plan(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    universe = load_universe(args.universe)
    store = SQLiteDataStore(settings.db_path)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    for item in universe:
        symbol = normalize_symbol(str(item["symbol"]))
        try:
            bars = router.get_daily_bars(symbol, args.start, args.end)
            store.upsert_daily_bars(bars)
            bars_by_symbol[symbol] = bars
        except Exception as exc:
            cached = store.load_daily_bars(symbol, start=args.start, end=args.end)
            if cached.empty:
                errors.append({"symbol": symbol, "error": str(exc)})
            else:
                bars_by_symbol[symbol] = cached
                errors.append({"symbol": symbol, "error": f"used_cached_data_after_fetch_error: {exc}"})
    plan = build_next_day_plan(universe, bars_by_symbol)
    csv_path, md_path = write_plan_reports(plan, settings.reports_dir)
    result = {
        "evaluated": int(len(plan)),
        "candidates": int((plan["action"] == "candidate").sum()) if "action" in plan else 0,
        "watch": int((plan["action"] == "watch_if_trigger").sum()) if "action" in plan else 0,
        "errors": errors,
        "csv": str(csv_path),
        "markdown": str(md_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not plan.empty else 2


def _backtest(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    bars = router.get_daily_bars(args.symbol, args.start, args.end)
    SQLiteDataStore(settings.db_path).upsert_daily_bars(bars)
    frame, metrics = run_backtest(bars)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = settings.reports_dir / f"backtest_{args.symbol.replace('.', '_')}_{stamp}.csv"
    frame.to_csv(output, index=False, encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"output={output}")
    return 0


def _macro(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    data = router.get_fred_series(args.series_id, start=args.start, end=args.end)
    output = settings.cache_dir / f"fred_{args.series_id}_{args.start or 'start'}_{args.end or 'end'}.csv"
    data.to_csv(output, index=False, encoding="utf-8")
    print(f"rows={len(data)} output={output}")
    return 0


def _qmt_positions(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    source = "terminal"
    raw_copy = None
    if args.file:
        path = Path(args.file).resolve() if args.file else settings.qmt_position_export
        if path is None:
            raise SystemExit("Provide --file or QMT_POSITION_EXPORT in .env")
        payload = import_position_export(path, settings.qmt_position_snapshot_path, settings.qmt_position_snapshot_csv_path)
        frame = load_position_export(path)
        output = settings.cache_dir / f"qmt_positions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        frame.to_csv(output, index=False, encoding="utf-8-sig")
        raw_copy = str(output)
        source = "export_file"
    else:
        try:
            payload = import_terminal_positions(
                sdk_path=settings.qmt_sdk_path,
                userdata_path=settings.qmt_userdata_path,
                account_id=settings.qmt_account_id,
                snapshot_path=settings.qmt_position_snapshot_path,
                csv_path=settings.qmt_position_snapshot_csv_path,
            )
        except QmtUnavailable as exc:
            if settings.qmt_position_export is None:
                raise SystemExit(f"QMT positions unavailable: {exc}") from exc
            payload = import_position_export(
                settings.qmt_position_export,
                settings.qmt_position_snapshot_path,
                settings.qmt_position_snapshot_csv_path,
            )
            frame = load_position_export(settings.qmt_position_export)
            output = settings.cache_dir / f"qmt_positions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            frame.to_csv(output, index=False, encoding="utf-8-sig")
            raw_copy = str(output)
            source = "export_file"
    print(
        json.dumps(
            {
                "rows": payload["rows"],
                "source": source,
                "source_file": payload["source_file"],
                "snapshot": str(settings.qmt_position_snapshot_path),
                "csv": str(settings.qmt_position_snapshot_csv_path),
                "raw_copy": raw_copy,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _qmt_doctor(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    symbols = _qmt_symbols(args.symbols, settings.qmt_realtime_symbols)
    provider = QmtProvider(settings.qmt_sdk_path)
    status = provider.probe(symbols=symbols)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def _qmt_snapshot(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    symbols = _qmt_symbols(args.symbols, settings.qmt_realtime_symbols)
    provider = QmtProvider(settings.qmt_sdk_path)
    try:
        payload = write_realtime_snapshot(settings.qmt_realtime_path, provider, symbols)
    except (QmtUnavailable, FileNotFoundError, ModuleNotFoundError) as exc:
        raise SystemExit(f"QMT realtime unavailable: {exc}. Configure QMT_SDK_PATH or install XtQuant for this Python runtime.")
    print(json.dumps({"output": str(settings.qmt_realtime_path), "updated_at": payload["updated_at"], "symbols": symbols}, ensure_ascii=False, indent=2))
    return 0


def _qmt_watch(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    symbols = _qmt_symbols(args.symbols, settings.qmt_realtime_symbols)
    provider = QmtProvider(settings.qmt_sdk_path)
    try:
        watch_realtime_snapshot(
            settings.qmt_realtime_path,
            provider,
            symbols,
            interval=args.interval,
            iterations=args.iterations,
        )
    except (QmtUnavailable, FileNotFoundError, ModuleNotFoundError) as exc:
        raise SystemExit(f"QMT realtime unavailable: {exc}. Configure QMT_SDK_PATH or install XtQuant for this Python runtime.")
    return 0


def _qmt_symbols(raw: str | None, defaults: tuple[str, ...]) -> list[str]:
    if raw:
        symbols = [item.strip().upper() for item in re.split(r"[\s,;]+", raw) if item.strip()]
    else:
        symbols = list(defaults)
    if not symbols:
        raise SystemExit("Provide --symbols or QMT_REALTIME_SYMBOLS in .env")
    return symbols


def _intraday_monitor(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    summary = _run_intraday_cycle(
        settings=settings,
        plan_arg=args.plan,
        write_alerts=not args.no_alerts,
        write_reports=True,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _intraday_watch(args: argparse.Namespace, settings, router: MarketDataRouter) -> int:
    count = 0
    while args.iterations is None or count < args.iterations:
        summary = _run_intraday_cycle(
            settings=settings,
            plan_arg=args.plan,
            write_alerts=not args.no_alerts,
            write_reports=args.write_reports,
        )
        print(json.dumps(_watch_line(summary), ensure_ascii=False), flush=True)
        count += 1
        if args.iterations is not None and count >= args.iterations:
            break
        time.sleep(max(args.interval, 0))
    return 0


def _run_intraday_cycle(
    *,
    settings,
    plan_arg: str | None,
    write_alerts: bool,
    write_reports: bool,
) -> dict[str, object]:
    plan_path = Path(plan_arg).resolve() if plan_arg else latest_plan_path(settings.reports_dir)
    if plan_path is None:
        raise SystemExit("No plan CSV found. Run plan first.")
    snapshot = read_realtime_snapshot(settings.qmt_realtime_path)
    monitor = build_intraday_monitor(load_plan(plan_path), snapshot)
    alerts = append_intraday_alerts(monitor, plan_path, settings.intraday_alert_log_path) if write_alerts else []
    status = write_intraday_status(monitor, plan_path, snapshot, settings.intraday_status_path, alerts)
    summary: dict[str, object] = {
        "checked_at": status["checked_at"],
        "rows": status["rows"],
        "triggered": status["triggered"],
        "invalidated": status["invalidated"],
        "gap_skip": status["gap_skip"],
        "waiting": status["waiting"],
        "no_tick": status["no_tick"],
        "not_monitoring": status["not_monitoring"],
        "new_alerts": len(alerts),
        "alert_log": str(settings.intraday_alert_log_path),
        "status": str(settings.intraday_status_path),
        "plan": str(plan_path),
        "snapshot": str(settings.qmt_realtime_path),
    }
    if write_reports:
        csv_path, md_path = write_intraday_reports(monitor, settings.reports_dir)
        summary["csv"] = str(csv_path)
        summary["markdown"] = str(md_path)
    return summary


def _watch_line(summary: dict[str, object]) -> dict[str, object]:
    return {
        "checked_at": summary.get("checked_at"),
        "triggered": summary.get("triggered", 0),
        "invalidated": summary.get("invalidated", 0),
        "gap_skip": summary.get("gap_skip", 0),
        "waiting": summary.get("waiting", 0),
        "new_alerts": summary.get("new_alerts", 0),
        "plan": Path(str(summary.get("plan", ""))).name,
    }


def _write_scan_markdown(path: Path, result: pd.DataFrame, errors: list[dict[str, str]]) -> None:
    lines = [
        "# Short-Term Scan",
        "",
        "This report is research output only. It does not place orders or size positions by amount.",
        "",
    ]
    if result.empty:
        lines.append("No candidates were generated.")
    else:
        view = result.copy()
        for column in ["stop_loss_pct", "take_profit_pct", "position_weight_cap"]:
            if column in view:
                view[column] = view[column].map(lambda x: f"{float(x):.2%}" if pd.notna(x) else "")
        lines.extend(_markdown_table(view))
    if errors:
        lines.extend(["", "## Data Errors", ""])
        for error in errors:
            lines.append(f"- {error['symbol']}: {error['error']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    columns = [str(column) for column in frame.columns]
    rows = [["" if pd.isna(value) else str(value) for value in row] for row in frame.to_numpy()]
    widths = [
        max(len(columns[index]), *(len(row[index]) for row in rows)) if rows else len(columns[index])
        for index in range(len(columns))
    ]

    def render(values: list[str]) -> str:
        return "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(values)) + " |"

    output = [render(columns), "| " + " | ".join("-" * width for width in widths) + " |"]
    output.extend(render(row) for row in rows)
    return output


if __name__ == "__main__":
    raise SystemExit(main())
