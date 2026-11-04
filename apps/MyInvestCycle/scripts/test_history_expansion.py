from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data_expansion.coverage_planner import build_expansion_plan
from data_expansion.expansion_audit import build_history_expansion_audit


def main() -> None:
    plan = build_expansion_plan(target_start="20150101", target_end="20260708")
    assert plan["constraints"]["no_strategy_rule_change"] is True
    assert plan["constraints"]["no_allocation_change"] is True
    assert plan["targets"]

    payload = build_history_expansion_audit(target_start="20150101", target_end="20260708")
    assert payload["audit_status"] == "pass"
    assert payload["constraints"]["no_strategy_rule_change"] is True
    assert payload["constraints"]["no_threshold_tuning"] is True
    assert payload["constraints"]["no_new_alpha_factor"] is True
    assert payload["after"]["start"] == "20150105"
    assert payload["after"]["end"] >= "20260707"
    assert isinstance(payload["known_gaps"], list)
    assert payload["coverage_status"] in {"pass", "pass_with_known_gaps"}
    if payload["known_gaps"]:
        assert payload["full_cycle_ready"] is False
    print("test_history_expansion ok")


if __name__ == "__main__":
    main()
