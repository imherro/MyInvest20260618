from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from macro.macro_loader import DEFAULT_MACRO_INDICATORS
from macro.release_calendar import is_record_available
from macro.schema import MacroIndicatorRecord, normalize_date


@dataclass(frozen=True)
class MacroDataIssue:
    indicator: str
    status: str
    issue_type: str
    message: str
    observation_date: str | None = None
    release_date: str | None = None
    effective_date: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "indicator": self.indicator,
            "status": self.status,
            "issue_type": self.issue_type,
            "message": self.message,
        }
        if self.observation_date is not None:
            payload["observation_date"] = self.observation_date
        if self.release_date is not None:
            payload["release_date"] = self.release_date
        if self.effective_date is not None:
            payload["effective_date"] = self.effective_date
        return payload


def flatten_records(records_by_indicator: Mapping[str, Iterable[MacroIndicatorRecord]]) -> list[MacroIndicatorRecord]:
    records: list[MacroIndicatorRecord] = []
    for items in records_by_indicator.values():
        records.extend(items)
    return records


def check_missing(
    records_by_indicator: Mapping[str, Iterable[MacroIndicatorRecord]],
    required_indicators: Iterable[str] = DEFAULT_MACRO_INDICATORS,
) -> list[MacroDataIssue]:
    issues: list[MacroDataIssue] = []
    for indicator in required_indicators:
        if not list(records_by_indicator.get(indicator, [])):
            issues.append(
                MacroDataIssue(
                    indicator=indicator,
                    status="missing",
                    issue_type="missing_indicator",
                    message="No local macro records found for the requested range.",
                )
            )
    return issues


def check_date_consistency(records: Iterable[MacroIndicatorRecord]) -> list[MacroDataIssue]:
    issues: list[MacroDataIssue] = []
    for record in records:
        if record.observation_date > record.release_date:
            issues.append(
                MacroDataIssue(
                    indicator=record.indicator,
                    status="invalid",
                    issue_type="release_before_observation",
                    message="release_date is earlier than observation_date.",
                    observation_date=record.observation_date,
                    release_date=record.release_date,
                    effective_date=record.effective_date,
                )
            )
        if record.effective_date < record.release_date:
            issues.append(
                MacroDataIssue(
                    indicator=record.indicator,
                    status="invalid",
                    issue_type="effective_before_release",
                    message="effective_date is earlier than release_date.",
                    observation_date=record.observation_date,
                    release_date=record.release_date,
                    effective_date=record.effective_date,
                )
            )
    return issues


def check_future_leakage(
    records: Iterable[MacroIndicatorRecord],
    decision_date: str | int | None = None,
) -> list[MacroDataIssue]:
    if decision_date is None:
        return []

    decision = normalize_date(decision_date)
    issues: list[MacroDataIssue] = []
    for record in records:
        if not is_record_available(record, decision):
            issues.append(
                MacroDataIssue(
                    indicator=record.indicator,
                    status="invalid",
                    issue_type="future_leakage",
                    message=f"Record is not knowable on decision_date={decision}.",
                    observation_date=record.observation_date,
                    release_date=record.release_date,
                    effective_date=record.effective_date,
                )
            )
    return issues


def audit_macro_records(
    records_by_indicator: Mapping[str, Iterable[MacroIndicatorRecord]],
    *,
    required_indicators: Iterable[str] = DEFAULT_MACRO_INDICATORS,
    decision_date: str | int | None = None,
) -> dict[str, object]:
    required = list(required_indicators)
    normalized_records = {
        indicator: list(items)
        for indicator, items in records_by_indicator.items()
    }
    records = flatten_records(normalized_records)
    missing_issues = check_missing(normalized_records, required)
    date_issues = check_date_consistency(records)
    leakage_issues = check_future_leakage(records, decision_date)
    hard_issues = [*date_issues, *leakage_issues]

    available_indicators = sorted(
        indicator
        for indicator in required
        if list(records_by_indicator.get(indicator, []))
    )
    missing_indicators = [issue.indicator for issue in missing_issues]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "indicators_total": len(required),
        "records_total": len(records),
        "available": len(available_indicators),
        "available_indicators": available_indicators,
        "missing": len(missing_indicators),
        "missing_indicators": missing_indicators,
        "future_leakage": bool(leakage_issues),
        "future_leakage_issues": [issue.to_dict() for issue in leakage_issues],
        "date_consistency_issues": [issue.to_dict() for issue in date_issues],
        "issues": [issue.to_dict() for issue in [*missing_issues, *hard_issues]],
        "impact": "weights_adjustment_required" if missing_indicators else "none",
        "status": "fail" if hard_issues else "pass",
    }
