from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from engine.hazard_model_evaluator import evaluate_hazard_model, save_evaluation_report
from engine.hazard_model_trainer import load_hazard_dataset, rows_to_matrix, time_series_split


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -50.0, 50.0)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained structural hazard model.")
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20260624")
    parser.add_argument("--dataset", default=str(DATA_DIR / "structural_hazard_dataset.json"))
    parser.add_argument("--model-file", default=str(DATA_DIR / "hazard_model_logistic.json"))
    parser.add_argument("--output", default=str(DATA_DIR / "hazard_model_evaluation.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_payload = json.loads(Path(args.model_file).read_text(encoding="utf-8"))
    model = model_payload["model"]
    split_config = model_payload["split"]
    feature_names = model["feature_names"]

    rows = load_hazard_dataset(args.dataset, start=args.start, end=args.end)
    split = time_series_split(rows, train_end=split_config["train_end"])
    test_x, test_y, test_feature_rows = rows_to_matrix(split.test_rows, feature_names=feature_names)
    means = np.asarray(model["feature_means"], dtype=float)
    scales = np.asarray(model["feature_scales"], dtype=float)
    test_scaled = (test_x - means) / scales
    scores = _sigmoid(test_scaled @ np.asarray(model["coefficients"], dtype=float) + float(model["intercept"]))

    evaluation = evaluate_hazard_model(
        test_y,
        scores,
        positive_rate=float(split_config["train_positive_rate"]),
        feature_rows=test_feature_rows,
    )
    report = {
        "metadata": {
            "dataset": _display_path(args.dataset),
            "model_file": _display_path(args.model_file),
            "start": args.start,
            "end": args.end,
            "model": model["type"],
        },
        "split": split_config,
        "evaluation": evaluation,
        "success_criteria": {
            "auc_minimum": 0.55,
            "lift_minimum": 1.1,
            "auc_status": "pass" if (evaluation["model"]["roc_auc"] or 0.0) > 0.55 else "fail",
            "lift_status": "pass" if (evaluation["model"]["lift_vs_random"] or 0.0) > 1.1 else "fail",
        },
    }
    report_path = save_evaluation_report(report, args.output)
    print(json.dumps({"evaluation_output": _display_path(report_path), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
