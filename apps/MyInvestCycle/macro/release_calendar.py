from __future__ import annotations

from macro.schema import MacroIndicatorRecord, normalize_date


def is_available(release_date: str | int, trading_date: str | int) -> bool:
    """Return whether a release was knowable on the decision/trading date."""
    return normalize_date(release_date) <= normalize_date(trading_date)


def is_record_available(record: MacroIndicatorRecord, decision_date: str | int) -> bool:
    decision = normalize_date(decision_date)
    return record.release_date <= decision and record.effective_date <= decision


def filter_available_records(
    records: list[MacroIndicatorRecord],
    decision_date: str | int,
) -> list[MacroIndicatorRecord]:
    return [record for record in records if is_record_available(record, decision_date)]
