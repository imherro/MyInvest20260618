from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.indicator_registry import get_all_indicator_definitions


REQUIRED_FIELDS = (
    "name",
    "category",
    "frequency",
    "source",
    "release_lag_days",
    "importance",
    "fallback_policy",
)


def main() -> int:
    definitions = get_all_indicator_definitions()
    issues: list[dict[str, object]] = []
    categories: dict[str, int] = {}
    missing_source = 0
    missing_adapter = 0

    for definition in definitions:
        payload = definition.to_dict()
        categories[definition.category] = categories.get(definition.category, 0) + 1
        for field in REQUIRED_FIELDS:
            if payload.get(field) in ("", None):
                issues.append({"indicator": definition.name, "issue": f"missing_{field}"})
        if not definition.source_detail:
            missing_source += 1
        if definition.adapter == "none":
            missing_adapter += 1

    report = {
        "total": len(definitions),
        "registered": len(definitions),
        "categories": categories,
        "missing_source": missing_source,
        "missing_adapter": missing_adapter,
        "issues": issues,
        "status": "pass" if not issues else "fail",
        "constraints": {
            "no_macro_score": True,
            "no_macro_state": True,
            "no_position_sizing": True,
            "no_etf_allocation": True,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
