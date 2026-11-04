from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


BAR_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume", "amount", "source"]


@dataclass
class SQLiteDataStore:
    path: Path

    def init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_bars (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, date)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    rows INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def upsert_daily_bars(self, bars: pd.DataFrame) -> int:
        if bars.empty:
            return 0
        missing = [column for column in BAR_COLUMNS if column not in bars.columns]
        if missing:
            raise ValueError(f"daily bars missing columns: {', '.join(missing)}")
        self.init_schema()
        frame = bars[BAR_COLUMNS].copy()
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        updated_at = datetime.now().isoformat(timespec="seconds")
        rows = [tuple(row) + (updated_at,) for row in frame.itertuples(index=False, name=None)]
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                """
                INSERT INTO daily_bars (
                    symbol, date, open, high, low, close, volume, amount, source, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                rows,
            )
            symbol = str(frame["symbol"].iloc[0])
            source = str(frame["source"].iloc[-1])
            conn.execute(
                """
                INSERT INTO ingestion_log (symbol, start_date, end_date, rows, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (symbol, str(frame["date"].min()), str(frame["date"].max()), len(frame), source, updated_at),
            )
        return len(frame)

    def load_daily_bars(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        self.init_schema()
        clauses = ["symbol = ?"]
        params: list[object] = [symbol]
        if start:
            clauses.append("date >= ?")
            params.append(_date_key(start))
        if end:
            clauses.append("date <= ?")
            params.append(_date_key(end))
        query = f"""
            SELECT symbol, date, open, high, low, close, volume, amount, source
            FROM daily_bars
            WHERE {' AND '.join(clauses)}
            ORDER BY date
        """
        with sqlite3.connect(self.path) as conn:
            frame = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
        return frame

    def coverage(self, limit: int = 20) -> pd.DataFrame:
        self.init_schema()
        with sqlite3.connect(self.path) as conn:
            return pd.read_sql_query(
                """
                SELECT
                    symbol,
                    COUNT(*) AS rows,
                    MIN(date) AS start_date,
                    MAX(date) AS end_date,
                    MAX(updated_at) AS updated_at,
                    GROUP_CONCAT(DISTINCT source) AS sources
                FROM daily_bars
                GROUP BY symbol
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                conn,
                params=[limit],
            )


def _date_key(value: str) -> str:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text
