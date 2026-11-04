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
from engine.hazard_model_trainer import (
    DEFAULT_FEATURES,
    load_hazard_dataset,
    save_model,
    train_logistic_model,
)


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a structural hazard model.")
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20260624")
    parser.add_argument("--dataset", default=str(DATA_DIR / "structural_hazard_dataset.json"))
    parser.add_argument("--model", choices=["logistic", "xgboost"], default="logistic")
    parser.add_argument("--train-end", default="20241231")
    parser.add_argument("--output", default=str(DATA_DIR / "hazard_model_logistic.json"))
    parser.add_argument("--evaluation-output", default=str(DATA_DIR / "hazard_model_evaluation.json"))
    parser.add_argument("--epochs", type=int, default=6000)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--l2", type=float, default=0.01)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.model == "xgboost":
        raise RuntimeError("XGBoost is optional and is not configured in this environment.")

    rows = load_hazard_dataset(args.dataset, start=args.start, end=args.end)
    result = train_logistic_model(
        rows,
        train_end=args.train_end,
        feature_names=DEFAULT_FEATURES,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2=args.l2,
    )
    model_payload = {
        "metadata": {
            "dataset": _display_path(args.dataset),
            "start": args.start,
            "end": args.end,
            "model": args.model,
        },
        "split": result["split"],
        "model": result["model"],
    }
    model_path = save_model(model_payload, args.output)

    evaluation = evaluate_hazard_model(
        result["test_labels"],
        result["test_scores"],
        positive_rate=float(result["split"]["train_positive_rate"]),
        feature_rows=result["test_feature_rows"],
    )
    report = {
        "metadata": {
            "dataset": _display_path(args.dataset),
            "model_file": _display_path(model_path),
            "start": args.start,
            "end": args.end,
            "model": args.model,
        },
        "split": result["split"],
        "evaluation": evaluation,
        "success_criteria": {
            "auc_minimum": 0.55,
            "lift_minimum": 1.1,
            "auc_status": "pass" if (evaluation["model"]["roc_auc"] or 0.0) > 0.55 else "fail",
            "lift_status": "pass" if (evaluation["model"]["lift_vs_random"] or 0.0) > 1.1 else "fail",
        },
    }
    report_path = save_evaluation_report(report, args.evaluation_output)
    print(json.dumps({"model_output": _display_path(model_path), "evaluation_output": _display_path(report_path), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
