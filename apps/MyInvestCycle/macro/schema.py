from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Mapping


QUALITY_STATUSES = {"valid", "missing", "estimated", "delayed", "invalid"}
DATE_PATTERN = re.compile(r"^\d{8}$")


def normalize_date(value: str | int | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")

    text = str(value).strip().replace("-", "").replace("/", "")
    if text.endswith(".0"):
        text = text[:-2]
    if not DATE_PATTERN.fullmatch(text):
        raise ValueError(f"Invalid date {value!r}; expected YYYYMMDD.")
    return text


@dataclass(frozen=True)
class MacroIndicatorRecord:
    indicator: str
    value: float | None
    observation_date: str
    release_date: str
    effective_date: str
    frequency: str
    source: str
    quality_status: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MacroIndicatorRecord":
        indicator = str(payload.get("indicator", "")).strip()
        if not indicator:
            raise ValueError("indicator is required.")

        raw_status = str(payload.get("quality_status", "valid")).strip().lower()
        if raw_status not in QUALITY_STATUSES:
            raise ValueError(f"quality_status must be one of {sorted(QUALITY_STATUSES)}.")

        raw_value = payload.get("value")
        value = None if raw_value in (None, "", "null") else float(raw_value)

        return cls(
            indicator=indicator,
            value=value,
            observation_date=normalize_date(payload.get("observation_date", "")),
            release_date=normalize_date(payload.get("release_date", "")),
            effective_date=normalize_date(payload.get("effective_date", "")),
            frequency=str(payload.get("frequency", "")).strip(),
            source=str(payload.get("source", "")).strip(),
            quality_status=raw_status,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "value": self.value,
            "observation_date": self.observation_date,
            "release_date": self.release_date,
            "effective_date": self.effective_date,
            "frequency": self.frequency,
            "source": self.source,
            "quality_status": self.quality_status,
        }

    @classmethod
    def missing(cls, indicator: str, *, as_of: str, source: str = "not_configured") -> "MacroIndicatorRecord":
        as_of_date = normalize_date(as_of)
        return cls(
            indicator=indicator,
            value=None,
            observation_date=as_of_date,
            release_date=as_of_date,
            effective_date=as_of_date,
            frequency="unknown",
            source=source,
            quality_status="missing",
        )
