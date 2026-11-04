from __future__ import annotations

from collections import Counter, defaultdict
from typing import Mapping, Sequence


PHASE_ORDER = {
    "EARLY_CYCLE": 0,
    "EXPANSION": 1,
    "ROTATION": 2,
    "LATE_CYCLE": 3,
    "CONTRACTION": 4,
    "UNKNOWN": -1,
}


EXPECTED_NEXT = {
    "EARLY_CYCLE": {"EARLY_CYCLE", "EXPANSION", "ROTATION"},
    "EXPANSION": {"EXPANSION", "ROTATION", "LATE_CYCLE"},
    "ROTATION": {"ROTATION", "LATE_CYCLE", "CONTRACTION", "EARLY_CYCLE"},
    "LATE_CYCLE": {"LATE_CYCLE", "CONTRACTION", "ROTATION"},
    "CONTRACTION": {"CONTRACTION", "EARLY_CYCLE", "UNKNOWN"},
    "UNKNOWN": {"UNKNOWN", "EARLY_CYCLE", "ROTATION", "CONTRACTION", "LATE_CYCLE"},
}


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def analyze_phase_transitions(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    transitions = []
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    previous = None
    for row in rows:
        phase = str(row.get("phase") or "UNKNOWN")
        if previous is not None:
            from_phase = str(previous.get("phase") or "UNKNOWN")
            matrix[from_phase][phase] += 1
            expected = phase in EXPECTED_NEXT.get(from_phase, set())
            transitions.append(
                {
                    "from_date": previous.get("date"),
                    "to_date": row.get("date"),
                    "from_phase": from_phase,
                    "to_phase": phase,
                    "expected_path": expected,
                    "phase_step": PHASE_ORDER.get(phase, -1) - PHASE_ORDER.get(from_phase, -1),
                }
            )
        previous = row

    unexpected = [item for item in transitions if not item["expected_path"]]
    large_jumps = [item for item in transitions if abs(int(item.get("phase_step") or 0)) >= 3]
    return {
        "transition_count": len(transitions),
        "transition_matrix": {key: dict(value) for key, value in sorted(matrix.items())},
        "expected_transition_rate": _share(len(transitions) - len(unexpected), len(transitions)),
        "unexpected_transition_count": len(unexpected),
        "large_jump_count": len(large_jumps),
        "unexpected_transition_distribution": _distribution(
            f"{item['from_phase']}->{item['to_phase']}" for item in unexpected
        ),
        "sample_unexpected_transitions": unexpected[:12],
        "sample_large_jumps": large_jumps[:12],
    }
