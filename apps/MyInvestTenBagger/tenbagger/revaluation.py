"""Universe expansion re-evaluation for TASK U2."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.config import DEFAULT_REPORT_DIR


TASK3_REPORT = "task3_screener_summary.json"
TASK7_REPORT = "task7_structural_validation_summary.json"
TASK8_REPORT = "task8_regime_summary.json"
REEVALUATION_JSON = "universe_revaluation_summary.json"
REEVALUATION_MARKDOWN = "TASK_U2_REEVALUATION.md"


@dataclass(frozen=True)
class UniverseLevelSnapshot:
    level: str
    report_dir: str | None
    missing_reports: list[str]
    universe_size: int
    stock_count: int
    candidate_count: int
    candidate_density: float
    sector_distribution: dict[str, float]
    ic_summary: dict[str, dict[str, Any]]
    alpha_classification: str | None
    alpha_criteria: dict[str, Any]
    regime_validation: dict[str, Any]

    @property
    def is_complete(self) -> bool:
        return TASK3_REPORT not in self.missing_reports


def run_universe_revaluation(
    report_root: Path | str = DEFAULT_REPORT_DIR,
    output_dir: Path | str = DEFAULT_REPORT_DIR,
    baseline_level: str = "dev",
    target_level: str = "research",
    baseline_report_dir: Path | str | None = None,
    target_report_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Compare pre-existing task reports across two universe levels."""

    report_root = Path(report_root)
    baseline = _load_snapshot(report_root, baseline_level, baseline_report_dir)
    target = _load_snapshot(report_root, target_level, target_report_dir)

    status = "complete" if baseline.is_complete and target.is_complete else "insufficient_data"
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK U2 - Full Universe Re-evaluation System",
        "status": status,
        "baseline_level": baseline_level,
        "target_level": target_level,
        "baseline": asdict(baseline),
        "target": asdict(target),
        "ic_shift": _metric_shift(baseline.ic_summary, target.ic_summary, "ic_mean", "ic_std"),
        "rankic_shift": _metric_shift(baseline.ic_summary, target.ic_summary, "rank_ic_mean", "rank_ic_std"),
        "candidate_density_shift": _candidate_density_shift(baseline, target),
        "regime_stability_shift": _regime_stability_shift(baseline, target),
    }
    result["structural_drift_score"] = 0.0 if status != "complete" else _structural_drift_score(result)
    result["structural_drift_conclusion"] = _drift_conclusion(result["structural_drift_score"], status)
    result["constraints"] = {
        "no_optimization": True,
        "no_factor_tuning": True,
        "statistical_comparison_only": True,
    }

    _write_outputs(result, Path(output_dir))
    return result


def _load_snapshot(
    report_root: Path,
    level: str,
    explicit_report_dir: Path | str | None,
) -> UniverseLevelSnapshot:
    report_dir = Path(explicit_report_dir) if explicit_report_dir is not None else _find_report_dir(report_root, level)
    reports = {}
    missing_reports = []
    for filename in (TASK3_REPORT, TASK7_REPORT, TASK8_REPORT):
        path = report_dir / filename if report_dir is not None else None
        if path is not None and path.exists():
            reports[filename] = json.loads(path.read_text(encoding="utf-8"))
        else:
            missing_reports.append(filename)

    task3 = reports.get(TASK3_REPORT, {})
    task7 = reports.get(TASK7_REPORT, {})
    task8 = reports.get(TASK8_REPORT, {})
    universe_meta = task3.get("universe") or task3.get("storage", {}).get("universe") or {}
    universe_size = int(universe_meta.get("stock_count") or universe_meta.get("universe_count") or task3.get("stock_count") or 0)
    stock_count = int(task3.get("stock_count") or 0)
    candidate_count = int(task3.get("candidate_count") or 0)
    denominator = universe_size or stock_count or 1
    return UniverseLevelSnapshot(
        level=level,
        report_dir=str(report_dir) if report_dir is not None else None,
        missing_reports=missing_reports,
        universe_size=universe_size,
        stock_count=stock_count,
        candidate_count=candidate_count,
        candidate_density=candidate_count / denominator,
        sector_distribution=_sector_distribution(task3.get("top_candidates", [])),
        ic_summary=_tenbagger_ic_summary(task3.get("ic_summary", {})),
        alpha_classification=task7.get("classification"),
        alpha_criteria=task7.get("criteria", {}),
        regime_validation=task8.get("validation", {}),
    )


def _find_report_dir(report_root: Path, level: str) -> Path | None:
    for candidate in (
        report_root / "universe" / level,
        report_root / level,
    ):
        if (candidate / TASK3_REPORT).exists():
            return candidate

    task3_path = report_root / TASK3_REPORT
    if task3_path.exists():
        try:
            task3 = json.loads(task3_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        report_level = (
            task3.get("universe", {}).get("level")
            or task3.get("storage", {}).get("universe", {}).get("level")
            or task3.get("storage", {}).get("universe_level")
        )
        if report_level == level or (report_level is None and level == "dev"):
            return report_root
    return None


def _tenbagger_ic_summary(ic_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for key, value in ic_summary.items():
        if key.startswith("tenbagger_score_") and isinstance(value, dict):
            result[key] = value
    return result


def _sector_distribution(rows: list[dict[str, Any]]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for row in rows:
        sector = str(row.get("industry") or "unknown")
        counts[sector] = counts.get(sector, 0) + 1
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {sector: count / total for sector, count in sorted(counts.items())}


def _metric_shift(
    baseline: dict[str, dict[str, Any]],
    target: dict[str, dict[str, Any]],
    mean_key: str,
    std_key: str,
) -> dict[str, Any]:
    rows = {}
    for key in sorted(set(baseline) & set(target)):
        old = baseline[key]
        new = target[key]
        old_mean = _float(old.get(mean_key))
        new_mean = _float(new.get(mean_key))
        old_std = _float(old.get(std_key))
        new_std = _float(new.get(std_key))
        old_n = max(int(old.get("observations") or 0), 1)
        new_n = max(int(new.get("observations") or 0), 1)
        standard_error = math.sqrt((old_std**2 / old_n) + (new_std**2 / new_n))
        delta = new_mean - old_mean
        z_score = delta / standard_error if standard_error > 0 else 0.0
        rows[key] = {
            "old": old_mean,
            "new": new_mean,
            "delta": delta,
            "old_std": old_std,
            "new_std": new_std,
            "old_observations": old_n,
            "new_observations": new_n,
            "z_score": z_score,
            "significant": abs(z_score) >= 1.96,
        }

    deltas = [abs(row["delta"]) for row in rows.values()]
    return {
        "metrics": rows,
        "mean_abs_delta": sum(deltas) / len(deltas) if deltas else 0.0,
        "significant_count": sum(1 for row in rows.values() if row["significant"]),
    }


def _candidate_density_shift(
    baseline: UniverseLevelSnapshot,
    target: UniverseLevelSnapshot,
) -> dict[str, Any]:
    sector_l1 = _distribution_l1(baseline.sector_distribution, target.sector_distribution)
    old_density = baseline.candidate_density
    new_density = target.candidate_density
    return {
        "old_density": old_density,
        "new_density": new_density,
        "delta": new_density - old_density,
        "old_candidate_count": baseline.candidate_count,
        "new_candidate_count": target.candidate_count,
        "old_universe_size": baseline.universe_size,
        "new_universe_size": target.universe_size,
        "sector_distribution_old": baseline.sector_distribution,
        "sector_distribution_new": target.sector_distribution,
        "sector_distribution_l1": sector_l1,
    }


def _regime_stability_shift(
    baseline: UniverseLevelSnapshot,
    target: UniverseLevelSnapshot,
) -> dict[str, Any]:
    old_auto = _float(baseline.regime_validation.get("regime_autocorrelation"))
    new_auto = _float(target.regime_validation.get("regime_autocorrelation"))
    old_transition = _float(baseline.regime_validation.get("transition_frequency"))
    new_transition = _float(target.regime_validation.get("transition_frequency"))
    return {
        "regime_autocorrelation_old": old_auto,
        "regime_autocorrelation_new": new_auto,
        "regime_autocorrelation_delta": new_auto - old_auto,
        "transition_frequency_old": old_transition,
        "transition_frequency_new": new_transition,
        "transition_frequency_delta": new_transition - old_transition,
    }


def _structural_drift_score(result: dict[str, Any]) -> float:
    rankic_component = min(1.0, result["rankic_shift"]["mean_abs_delta"] / 0.10)
    density = result["candidate_density_shift"]
    density_base = max(abs(density["old_density"]), 0.01)
    density_component = min(1.0, abs(density["delta"]) / density_base)
    sector_component = min(1.0, density["sector_distribution_l1"] / 2)
    regime_component = min(1.0, abs(result["regime_stability_shift"]["transition_frequency_delta"]) / 0.20)
    score = (
        rankic_component * 0.35
        + density_component * 0.25
        + sector_component * 0.20
        + regime_component * 0.20
    )
    return round(float(score), 4)


def _drift_conclusion(score: float, status: str) -> str:
    if status != "complete":
        return "insufficient_data"
    if score >= 0.65:
        return "high_structural_drift"
    if score >= 0.35:
        return "moderate_structural_drift"
    return "low_structural_drift"


def _distribution_l1(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    return float(sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys))


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _write_outputs(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / REEVALUATION_JSON).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / REEVALUATION_MARKDOWN).write_text(_markdown_report(result), encoding="utf-8")


def _markdown_report(result: dict[str, Any]) -> str:
    density = result["candidate_density_shift"]
    regime = result["regime_stability_shift"]
    lines = [
        "# TASK U2 Re-evaluation Report",
        "",
        f"- Generated at: {result['generated_at']}",
        f"- Status: {result['status']}",
        f"- Baseline: {result['baseline_level']}",
        f"- Target: {result['target_level']}",
        f"- Structural drift score: {result['structural_drift_score']}",
        f"- Conclusion: {result['structural_drift_conclusion']}",
        "",
        "## IC Shift",
        "",
    ]
    for key, row in result["ic_shift"]["metrics"].items():
        lines.append(
            f"- {key}: old={row['old']:.4f}, new={row['new']:.4f}, delta={row['delta']:.4f}, z={row['z_score']:.2f}, significant={row['significant']}"
        )
    lines.extend(["", "## RankIC Shift", ""])
    for key, row in result["rankic_shift"]["metrics"].items():
        lines.append(
            f"- {key}: old={row['old']:.4f}, new={row['new']:.4f}, delta={row['delta']:.4f}, z={row['z_score']:.2f}, significant={row['significant']}"
        )
    lines.extend(
        [
            "",
            "## Candidate Density",
            "",
            f"- Old density: {density['old_density']:.6f}",
            f"- New density: {density['new_density']:.6f}",
            f"- Delta: {density['delta']:.6f}",
            f"- Sector distribution L1: {density['sector_distribution_l1']:.4f}",
            "",
            "## Regime Stability",
            "",
            f"- Regime autocorrelation delta: {regime['regime_autocorrelation_delta']:.4f}",
            f"- Transition frequency delta: {regime['transition_frequency_delta']:.4f}",
            "",
            "## Constraints",
            "",
            "- No optimization was performed.",
            "- No factor structure was changed.",
            "- This report is a statistical comparison only.",
            "",
        ]
    )
    missing = result["baseline"]["missing_reports"] + result["target"]["missing_reports"]
    if missing:
        lines.extend(["## Missing Inputs", ""])
        for filename in sorted(set(missing)):
            lines.append(f"- {filename}")
        lines.append("")
    return "\n".join(lines)
