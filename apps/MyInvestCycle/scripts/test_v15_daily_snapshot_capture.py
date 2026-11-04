from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_daily_snapshot_capture,
    find_forbidden_output_keys,
    normalized_manifest_sha256,
    validate_v15_daily_snapshot_capture,
)
from strategy_rebase.daily_snapshot_capture import FORBIDDEN_OUTPUT_KEYS


CAPTURED_AT = "2026-07-20T20:00:00+08:00"


def _write_source(root: Path, relative_path: str, content: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _fixture_root(*, missing_structural: bool = False) -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    _write_source(root, "data/macro_context_history.json", "{}\n")
    _write_source(
        root,
        "data/market_phase_snapshot.json",
        json.dumps({"current": {"phase": "LATE_CYCLE", "metrics": {"macro_state": "RECOVERY", "structural_state": "STRUCTURAL_BULL_ROTATION"}}}),
    )
    _write_source(root, "data/historical_style_context.json", "{}\n")
    if not missing_structural:
        _write_source(root, "data/structural_hazard_dataset.json", "[]\n")
    _write_source(root, "data/cache/index_daily_000300_SH.csv", "trade_date,close\n20260717,4000\n")
    return temporary


def test_missing_source_is_recorded_without_fake_file() -> None:
    with _fixture_root(missing_structural=True) as tmp:
        root = Path(tmp)
        manifest, status, decision = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
        )
        missing = [source for source in manifest["sources"] if source["snapshot_available"] is False]
        assert len(missing) == 1
        assert missing[0]["source_group"] == "structural_context"
        assert missing[0]["source_sha256"] is None
        assert not (root / missing[0]["snapshot_path"]).exists()
        assert manifest["missing_source_count"] == 1
        validate_v15_daily_snapshot_capture(manifest, status, decision, root_dir=root)


def test_copied_snapshot_hashes_recompute_and_match() -> None:
    with _fixture_root() as tmp:
        root = Path(tmp)
        manifest, status, decision = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
        )
        assert manifest["available_source_count"] == 5
        assert all(source["source_sha256"] == source["current_file_sha256"] for source in manifest["sources"])
        validate_v15_daily_snapshot_capture(manifest, status, decision, root_dir=root)


def test_manifest_sha256_is_normalized_and_stable() -> None:
    with _fixture_root() as tmp:
        manifest, _, _ = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=tmp
        )
        assert manifest["manifest_sha256"] == normalized_manifest_sha256(manifest)
        reordered = {key: manifest[key] for key in reversed(list(manifest))}
        assert normalized_manifest_sha256(reordered) == manifest["manifest_sha256"]


def test_current_hash_is_snapshot_hash_only_for_available_forward_copy() -> None:
    with _fixture_root(missing_structural=True) as tmp:
        manifest, _, _ = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=tmp
        )
        for source in manifest["sources"]:
            if source["snapshot_available"]:
                assert source["source_sha256_origin"] == "daily_forward_snapshot_file"
                assert source["current_hash_is_historical_snapshot"] is True
                assert source["hash_verified"] is True
            else:
                assert source["source_sha256_origin"] is None
                assert source["current_hash_is_historical_snapshot"] is False
                assert source["hash_verified"] is False


def test_forward_decision_has_no_forbidden_output_keys() -> None:
    with _fixture_root() as tmp:
        _, _, decision = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=tmp
        )
        assert find_forbidden_output_keys(decision) == set()


def test_each_forbidden_output_key_is_rejected() -> None:
    with _fixture_root() as tmp:
        root = Path(tmp)
        manifest, status, decision = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
        )
        for key in FORBIDDEN_OUTPUT_KEYS:
            forged = deepcopy(decision)
            forged[key] = "forged"
            try:
                validate_v15_daily_snapshot_capture(manifest, status, forged, root_dir=root)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forbidden output key must fail: {key}")


def test_backtest_and_production_trade_cannot_be_enabled() -> None:
    with _fixture_root() as tmp:
        root = Path(tmp)
        manifest, status, decision = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
        )
        for target, key in ((manifest, "backtest_allowed"), (status, "backtest_allowed"), (manifest, "production_trade_enabled"), (status, "production_trade_enabled")):
            forged = deepcopy(target)
            forged[key] = True
            if target is manifest:
                forged["manifest_sha256"] = normalized_manifest_sha256(forged)
            forged_manifest = forged if target is manifest else manifest
            forged_status = forged if target is status else status
            try:
                validate_v15_daily_snapshot_capture(forged_manifest, forged_status, decision, root_dir=root)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"{key}=true must fail")


def test_same_date_capture_is_immutable() -> None:
    with _fixture_root() as tmp:
        root = Path(tmp)
        manifest, _, _ = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
        )
        original_hash = manifest["manifest_sha256"]
        _write_source(root, "data/macro_context_history.json", '{"changed": true}\n')
        repeated, status, decision = build_v15_daily_snapshot_capture(
            snapshot_date="20260720", captured_at="2026-07-20T21:00:00+08:00", root_dir=root
        )
        assert repeated["manifest_sha256"] == original_hash
        assert status["created_now"] is False
        validate_v15_daily_snapshot_capture(repeated, status, decision, root_dir=root)


def main() -> None:
    test_missing_source_is_recorded_without_fake_file()
    test_copied_snapshot_hashes_recompute_and_match()
    test_manifest_sha256_is_normalized_and_stable()
    test_current_hash_is_snapshot_hash_only_for_available_forward_copy()
    test_forward_decision_has_no_forbidden_output_keys()
    test_each_forbidden_output_key_is_rejected()
    test_backtest_and_production_trade_cannot_be_enabled()
    test_same_date_capture_is_immutable()
    print("test_v15_daily_snapshot_capture ok")


if __name__ == "__main__":
    main()
