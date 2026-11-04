from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.exposure_sensitivity import POLICY_VARIANTS
from backtest.walk_forward_validator import build_walk_forward_coverage_audit


def test_policy_variants_and_coverage_audit() -> None:
    assert {"baseline", "higher_participation", "conservative"} <= set(POLICY_VARIANTS)
    assert POLICY_VARIANTS["higher_participation"]["exposure_map"]["medium_high"] > POLICY_VARIANTS["baseline"]["exposure_map"]["medium_high"]
    assert POLICY_VARIANTS["conservative"]["exposure_map"]["medium"] < POLICY_VARIANTS["baseline"]["exposure_map"]["medium"]
    audit = build_walk_forward_coverage_audit(desired_start="20150101", desired_end="20260708")
    assert audit["policy"]["do_not_backfill_silently"] is True
    assert "industry_opportunity_proxy" in audit["series"]
    assert isinstance(audit["blockers"], list)


if __name__ == "__main__":
    test_policy_variants_and_coverage_audit()
    print("ok")
