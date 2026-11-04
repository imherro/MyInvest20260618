from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_late_cycle_overlay_manifest,
    build_v15_point_in_time_phase_rebuild_status,
    validate_v15_late_cycle_overlay_manifest,
    validate_v15_point_in_time_phase_rebuild_status,
    write_v15_late_cycle_overlay_manifest,
    write_v15_point_in_time_phase_rebuild_status,
)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_fixture_cannot_fake_verified_lineage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        phase = root / "phase.json"
        macro = root / "macro.json"
        style = root / "style.json"
        _write(phase, {"historical_replay": [{"date": "20240102", "phase": "EARLY_CYCLE"}]})
        _write(
            macro,
            {
                "rows": [
                    {
                        "date": "20240102",
                        "macro_context": {"PE_percentile": None, "PB_percentile": None, "ERP": None},
                        "data_quality": {"release_date_lte_signal_date": True, "effective_date_lte_signal_date": True},
                    }
                ]
            },
        )
        _write(
            style,
            {
                "rows": [
                    {
                        "date": "20240102",
                        "source": "historical_reconstruction_from_local_cache",
                        "data_quality": {"structural_features_available": False},
                    }
                ]
            },
        )
        payload = build_v15_point_in_time_phase_rebuild_status(
            phase_path=phase, macro_path=macro, style_path=style
        )
    assert payload["strict_point_in_time_phase_status"] == "gap_report_ready"
    assert payload["publication_time_lineage_verified"] is False
    assert payload["unverified_dates"] == ["20240102"]
    assert payload["gap_count"] >= 4
    assert payload["uses_future_returns"] is False
    assert payload["uses_reconstructed_labels"] is True
    assert payload["promotion_ready"] is False


def test_real_payload_and_manifest() -> None:
    status = build_v15_point_in_time_phase_rebuild_status()
    manifest = build_v15_late_cycle_overlay_manifest()
    audit = validate_v15_point_in_time_phase_rebuild_status(status)
    manifest_audit = validate_v15_late_cycle_overlay_manifest(manifest)
    assert status["summary"]["phase_row_count"] == 140
    assert status["summary"]["unverified_date_count"] == 140
    assert status["summary"]["macro_release_effective_safe_count"] == 140
    assert status["summary"]["valuation_available_count"] == 0
    assert status["summary"]["reconstructed_style_date_count"] == 140
    assert 0 < status["summary"]["structural_context_complete_count"] < 140
    assert status["publication_time_lineage_verified"] is False
    assert manifest["summary"]["feature_count"] == 6
    assert manifest["summary"]["backtest_allowed"] is False
    assert audit["audit_status"] == "passed"
    assert manifest_audit["audit_status"] == "passed"
    with tempfile.TemporaryDirectory() as tmp:
        assert write_v15_point_in_time_phase_rebuild_status(status, Path(tmp) / "status.json").exists()
        assert write_v15_late_cycle_overlay_manifest(manifest, Path(tmp) / "manifest.json").exists()


def main() -> None:
    test_fixture_cannot_fake_verified_lineage()
    test_real_payload_and_manifest()
    print("test_v15_point_in_time_phase_rebuild ok")


if __name__ == "__main__":
    main()
