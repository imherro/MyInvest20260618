from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from config import DATA_DIR


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_ROOT = DATA_DIR / "point_in_time_snapshots"
DEFAULT_STATUS_PATH = DATA_DIR / "v15_daily_snapshot_capture_status.json"
DEFAULT_DECISION_PATH = DATA_DIR / "v15_forward_paper_decision_latest.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

SOURCE_SPECS = (
    ("macro", "macro_context_history", "data/macro_context_history.json"),
    ("market_phase", "market_phase_snapshot", "data/market_phase_snapshot.json"),
    ("style_context", "historical_style_context", "data/historical_style_context.json"),
    ("structural_context", "structural_hazard_dataset", "data/structural_hazard_dataset.json"),
    ("broad_index", "index_daily_000300_SH", "data/cache/index_daily_000300_SH.csv"),
)

FORBIDDEN_OUTPUT_KEYS = {
    "stock_code",
    "stock_selection",
    "etf_code",
    "etf_mapping",
    "target_position",
    "position_weight",
    "portfolio_weight",
    "allocation",
    "buy_signal",
    "sell_signal",
    "trade_signal",
    "order",
    "broker_order",
    "rebalance_instruction",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_manifest_sha256(manifest: Mapping[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _repo_path(root_dir: Path, relative_path: str) -> Path:
    target = (root_dir / relative_path).resolve()
    if not target.is_relative_to(root_dir.resolve()):
        raise ValueError(f"path escapes repository root: {relative_path}")
    return target


def _current_capture_time() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _market_phase_readouts(root_dir: Path, manifest: Mapping[str, object]) -> dict[str, object]:
    sources = manifest.get("sources")
    market_phase = next(
        (
            source
            for source in sources
            if isinstance(source, Mapping)
            and source.get("source_name") == "market_phase_snapshot"
            and source.get("snapshot_available") is True
        ),
        None,
    ) if isinstance(sources, list) else None
    if not isinstance(market_phase, Mapping) or not market_phase.get("snapshot_path"):
        return {"macro_cycle": None, "drawdown_context": None, "structural_bull": None, "late_cycle_risk": None}

    payload = _read_json(_repo_path(root_dir, str(market_phase["snapshot_path"])))
    current = payload.get("current") if isinstance(payload.get("current"), Mapping) else {}
    metrics = current.get("metrics") if isinstance(current.get("metrics"), Mapping) else {}
    return {
        "macro_cycle": metrics.get("macro_state"),
        "drawdown_context": None,
        "structural_bull": metrics.get("structural_state"),
        "late_cycle_risk": current.get("phase"),
    }


def find_forbidden_output_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) in FORBIDDEN_OUTPUT_KEYS:
                found.add(str(key))
            found.update(find_forbidden_output_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(find_forbidden_output_keys(nested))
    return found


def build_v15_daily_snapshot_capture(
    *,
    snapshot_date: str | None = None,
    captured_at: str | None = None,
    root_dir: str | Path = ROOT_DIR,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    root = Path(root_dir).resolve()
    capture_time = datetime.fromisoformat(captured_at) if captured_at else _current_capture_time()
    date = snapshot_date or capture_time.strftime("%Y%m%d")
    if re.fullmatch(r"\d{8}", date) is None:
        raise ValueError("snapshot_date must use YYYYMMDD")
    captured_iso = capture_time.isoformat(timespec="seconds")
    snapshot_relative_dir = f"data/point_in_time_snapshots/{date}"
    snapshot_dir = _repo_path(root, snapshot_relative_dir)
    manifest_path = snapshot_dir / "manifest.json"
    created_now = not manifest_path.exists()

    if created_now:
        sources_dir = snapshot_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        sources: list[dict[str, object]] = []
        for source_group, source_name, original_relative_path in SOURCE_SPECS:
            original_path = _repo_path(root, original_relative_path)
            suffix = original_path.suffix
            snapshot_relative_path = f"{snapshot_relative_dir}/sources/{source_name}{suffix}"
            snapshot_path = _repo_path(root, snapshot_relative_path)
            available = original_path.is_file()
            entry: dict[str, object] = {
                "source_group": source_group,
                "source_name": source_name,
                "original_path": original_relative_path,
                "snapshot_path": snapshot_relative_path,
                "snapshot_available": available,
                "captured_at": captured_iso,
                "source_sha256": None,
                "source_sha256_origin": None,
                "current_file_sha256": None,
                "current_hash_is_historical_snapshot": False,
                "hash_verified": False,
                "missing_reason": None,
            }
            if available:
                shutil.copyfile(original_path, snapshot_path)
                source_hash = _sha256(snapshot_path)
                current_hash = _sha256(original_path)
                entry.update(
                    {
                        "source_sha256": source_hash,
                        "source_sha256_origin": "daily_forward_snapshot_file",
                        "current_file_sha256": current_hash,
                        "current_hash_is_historical_snapshot": source_hash == current_hash,
                        "hash_verified": source_hash == current_hash,
                    }
                )
            else:
                entry["missing_reason"] = "source_file_missing_at_capture_time"
            sources.append(entry)

        available_count = sum(1 for source in sources if source["snapshot_available"] is True)
        manifest: dict[str, object] = {
            "phase": "V15.7",
            "snapshot_date": date,
            "captured_at": captured_iso,
            "snapshot_mode": "daily_forward_capture",
            "source_count": len(sources),
            "available_source_count": available_count,
            "missing_source_count": len(sources) - available_count,
            "sources": sources,
            "manifest_sha256": None,
            "immutable_snapshot_created": True,
            "backtest_allowed": False,
            "paper_decision_allowed": True,
            "production_trade_enabled": False,
        }
        manifest["manifest_sha256"] = normalized_manifest_sha256(manifest)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        manifest = _read_json(manifest_path)

    decision: dict[str, object] = {
        "phase": "V15.7",
        "decision_date": str(manifest.get("snapshot_date") or date),
        "paper_only": True,
        "not_production_signal": True,
        "snapshot_manifest": f"{snapshot_relative_dir}/manifest.json",
        "snapshot_manifest_sha256": manifest.get("manifest_sha256"),
        "data_readiness": {
            "immutable_snapshot_created": manifest.get("immutable_snapshot_created") is True,
            "valuation_available": False,
            "late_cycle_overlay_ready": False,
            "strict_point_in_time_ready_for_backtest": False,
        },
        "readouts": _market_phase_readouts(root, manifest),
        "paper_decision": {
            "decision_status": "insufficient_for_trade_decision",
            "reason": "Forward snapshot captured, but valuation/late-cycle overlay and full PIT evidence are not ready.",
            "allowed_use": "forward_observation_only",
        },
        "constraints": {
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_position": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    status: dict[str, object] = {
        "phase": "V15.7",
        "snapshot_date": manifest.get("snapshot_date"),
        "captured_at": manifest.get("captured_at"),
        "snapshot_directory": snapshot_relative_dir,
        "manifest_path": f"{snapshot_relative_dir}/manifest.json",
        "manifest_sha256": manifest.get("manifest_sha256"),
        "source_count": manifest.get("source_count"),
        "available_source_count": manifest.get("available_source_count"),
        "missing_source_count": manifest.get("missing_source_count"),
        "immutable_snapshot_created": manifest.get("immutable_snapshot_created"),
        "created_now": created_now,
        "paper_decision_status": decision["paper_decision"]["decision_status"],
        "backtest_allowed": False,
        "production_trade_enabled": False,
        "summary": {
            "phase": "V15.7",
            "snapshot_date": manifest.get("snapshot_date"),
            "available_source_count": manifest.get("available_source_count"),
            "missing_source_count": manifest.get("missing_source_count"),
            "manifest_sha256": manifest.get("manifest_sha256"),
            "paper_decision_status": decision["paper_decision"]["decision_status"],
            "paper_only": True,
            "backtest_allowed": False,
            "production_trade_enabled": False,
        },
    }
    validate_v15_daily_snapshot_capture(manifest, status, decision, root_dir=root)
    return manifest, status, decision


def validate_v15_daily_snapshot_capture(
    manifest: Mapping[str, object],
    status: Mapping[str, object],
    decision: Mapping[str, object],
    *,
    root_dir: str | Path = ROOT_DIR,
) -> None:
    root = Path(root_dir).resolve()
    if manifest.get("phase") != "V15.7" or status.get("phase") != "V15.7" or decision.get("phase") != "V15.7":
        raise AssertionError("phase must be V15.7")
    if manifest.get("snapshot_mode") != "daily_forward_capture":
        raise AssertionError("snapshot mode must be daily_forward_capture")
    if manifest.get("manifest_sha256") != normalized_manifest_sha256(manifest):
        raise AssertionError("manifest_sha256 must match normalized manifest payload")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != len(SOURCE_SPECS):
        raise AssertionError("manifest must contain every configured source")
    available_count = 0
    for source in sources:
        if not isinstance(source, Mapping):
            raise AssertionError("source entry must be an object")
        available = source.get("snapshot_available") is True
        snapshot_path = _repo_path(root, str(source.get("snapshot_path") or ""))
        if available:
            available_count += 1
            source_hash = source.get("source_sha256")
            if not isinstance(source_hash, str) or SHA256_PATTERN.fullmatch(source_hash) is None:
                raise AssertionError("available source must have a valid SHA-256")
            if not snapshot_path.is_file() or _sha256(snapshot_path) != source_hash:
                raise AssertionError("snapshot file hash verification failed")
            if source.get("source_sha256_origin") != "daily_forward_snapshot_file":
                raise AssertionError("snapshot hash origin is invalid")
            if source.get("current_file_sha256") != source_hash:
                raise AssertionError("captured current file hash must match snapshot hash")
            if source.get("current_hash_is_historical_snapshot") is not True or source.get("hash_verified") is not True:
                raise AssertionError("available forward snapshot must be hash verified")
        else:
            if snapshot_path.exists():
                raise AssertionError("missing source must not create a fake snapshot file")
            if source.get("source_sha256") is not None or source.get("hash_verified") is not False:
                raise AssertionError("missing source cannot claim a verified hash")
    if manifest.get("source_count") != len(sources):
        raise AssertionError("source_count is invalid")
    if manifest.get("available_source_count") != available_count:
        raise AssertionError("available_source_count is invalid")
    if manifest.get("missing_source_count") != len(sources) - available_count:
        raise AssertionError("missing_source_count is invalid")
    if manifest.get("immutable_snapshot_created") is not True:
        raise AssertionError("immutable snapshot must be created")
    if manifest.get("backtest_allowed") is not False or status.get("backtest_allowed") is not False:
        raise AssertionError("V15.7 cannot allow backtesting")
    if manifest.get("production_trade_enabled") is not False or status.get("production_trade_enabled") is not False:
        raise AssertionError("production trading must be disabled")
    if decision.get("paper_only") is not True or decision.get("not_production_signal") is not True:
        raise AssertionError("forward decision must remain paper-only")
    if decision.get("snapshot_manifest_sha256") != manifest.get("manifest_sha256"):
        raise AssertionError("decision must reference the verified manifest hash")
    if find_forbidden_output_keys(decision):
        raise AssertionError("forward paper decision contains forbidden output keys")
    constraints = decision.get("constraints") if isinstance(decision.get("constraints"), Mapping) else {}
    for key in (
        "does_not_run_backtest",
        "does_not_optimize_parameters",
        "does_not_generate_position",
        "does_not_generate_portfolio_weight",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ):
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")


def write_v15_daily_snapshot_capture(
    status: Mapping[str, object],
    decision: Mapping[str, object],
    *,
    status_path: str | Path = DEFAULT_STATUS_PATH,
    decision_path: str | Path = DEFAULT_DECISION_PATH,
) -> tuple[Path, Path]:
    status_target = Path(status_path)
    decision_target = Path(decision_path)
    status_target.parent.mkdir(parents=True, exist_ok=True)
    decision_target.parent.mkdir(parents=True, exist_ok=True)
    status_target.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decision_target.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status_target, decision_target
