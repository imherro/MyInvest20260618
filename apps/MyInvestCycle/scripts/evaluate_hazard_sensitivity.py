from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from engine.hazard_model_evaluator import evaluate_hazard_model, save_evaluation_report
from engine.hazard_model_trainer import train_logistic_model
from engine.regime_hazard_labeler import hazard_label_distribution
from engine.regime_hazard_labeler_v2 import build_structural_hazard_dataset


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def _parse_int_list(value: str) -> list[int]:
    parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not parsed:
        raise argparse.ArgumentTypeError("Expected at least one integer")
    return parsed


def _load_raw_regime_items(path: str | Path) -> list[dict[str, object]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    items: list[dict[str, object]] = []
    for row in rows:
        features = row["features"]
        items.append(
            {
                "trade_date": row["date"],
                "regime": row["regime"],
                "trend_score": features["trend"],
                "breadth_score": features["breadth"],
                "liquidity_score": features["liquidity"],
                "volatility_score": features["volatility"],
                "regime_score": features.get("regime_score", 0.0),
                "confidence": features.get("confidence", 0.0),
            }
        )
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate hazard model stability across structural label parameters.")
    parser.add_argument("--raw-dataset", default=str(DATA_DIR / "hazard_dataset.json"))
    parser.add_argument("--output", default=str(DATA_DIR / "hazard_model_sensitivity.json"))
    parser.add_argument("--train-end", default="20241231")
    parser.add_argument("--smooth-radius", type=int, default=3)
    parser.add_argument("--persistence-days", type=int, default=3)
    parser.add_argument("--forward-windows", type=_parse_int_list, default=[5, 10])
    parser.add_argument("--min-break-gaps", type=_parse_int_list, default=[10, 20, 30])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_items = _load_raw_regime_items(args.raw_dataset)
    results: list[dict[str, object]] = []
    for forward_window in args.forward_windows:
        for min_break_gap in args.min_break_gaps:
            dataset = build_structural_hazard_dataset(
                raw_items,
                smooth_radius=args.smooth_radius,
                persistence_days=args.persistence_days,
                forward_window=forward_window,
                min_break_gap=min_break_gap,
            )
            distribution = hazard_label_distribution(dataset)
            trained = train_logistic_model(dataset, train_end=args.train_end)
            evaluation = evaluate_hazard_model(
                trained["test_labels"],
                trained["test_scores"],
                positive_rate=float(trained["split"]["train_positive_rate"]),
                feature_rows=trained["test_feature_rows"],
            )
            results.append(
                {
                    "parameters": {
                        "smooth_radius": int(args.smooth_radius),
                        "persistence_days": int(args.persistence_days),
                        "forward_window": int(forward_window),
                        "min_break_gap": int(min_break_gap),
                    },
                    "label_distribution": distribution,
                    "split": trained["split"],
                    "model": {
                        "roc_auc": evaluation["model"]["roc_auc"],
                        "precision": evaluation["model"]["precision"],
                        "recall": evaluation["model"]["recall"],
                        "lift_vs_random": evaluation["model"]["lift_vs_random"],
                    },
                    "baselines": {
                        "random": evaluation["baselines"]["random"],
                        "always_zero": evaluation["baselines"]["always_zero"],
                        "volatility_only": {
                            "roc_auc": evaluation["baselines"]["volatility_only"]["roc_auc"],
                            "precision": evaluation["baselines"]["volatility_only"]["precision"],
                            "recall": evaluation["baselines"]["volatility_only"]["recall"],
                            "lift_vs_random": evaluation["baselines"]["volatility_only"]["lift_vs_random"],
                        },
                    },
                    "baseline_gap": evaluation["baseline_gap"],
                }
            )

    auc_values = [float(result["model"]["roc_auc"]) for result in results if result["model"]["roc_auc"] is not None]
    lift_values = [
        float(result["model"]["lift_vs_random"])
        for result in results
        if result["model"]["lift_vs_random"] is not None
    ]
    report = {
        "metadata": {
            "raw_dataset": _display_path(args.raw_dataset),
            "train_end": args.train_end,
            "smooth_radius": int(args.smooth_radius),
            "persistence_days": int(args.persistence_days),
            "forward_windows": args.forward_windows,
            "min_break_gaps": args.min_break_gaps,
        },
        "summary": {
            "runs": int(len(results)),
            "auc_min": round(min(auc_values), 6) if auc_values else None,
            "auc_max": round(max(auc_values), 6) if auc_values else None,
            "lift_min": round(min(lift_values), 6) if lift_values else None,
            "lift_max": round(max(lift_values), 6) if lift_values else None,
            "all_auc_above_0_55": all(value > 0.55 for value in auc_values),
            "all_lift_above_1_1": all(value > 1.1 for value in lift_values),
        },
        "results": results,
    }
    output_path = save_evaluation_report(report, args.output)
    print(json.dumps({"output": _display_path(output_path), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
