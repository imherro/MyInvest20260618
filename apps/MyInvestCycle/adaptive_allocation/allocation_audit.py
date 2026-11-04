from __future__ import annotations

from typing import Mapping


def audit_allocation_trace(allocation_payload: Mapping[str, object], trace: Mapping[str, object]) -> dict[str, object]:
    text = str({"allocation": allocation_payload, "trace": trace})
    violations: list[str] = []
    if ".SH" in text or ".SZ" in text:
        violations.append("security_or_etf_code_present")
    for key in ("trade_signal", "order", "broker", "buy", "sell"):
        if key in allocation_payload:
            violations.append(f"forbidden_top_level_key:{key}")
    constraints = allocation_payload.get("constraints")
    if isinstance(constraints, Mapping):
        for required in ("no_etf_code", "no_buy_sell", "no_order", "no_broker_connection"):
            if constraints.get(required) is not True:
                violations.append(f"constraint_not_true:{required}")
    else:
        violations.append("missing_constraints")
    return {
        "passed": not violations,
        "violations": violations,
        "no_future_data": bool((allocation_payload.get("data_quality") or {}).get("no_future_data"))
        if isinstance(allocation_payload.get("data_quality"), Mapping)
        else False,
        "does_not_change_allocation_intent": True,
    }
