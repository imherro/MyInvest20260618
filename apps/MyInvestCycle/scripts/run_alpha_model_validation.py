from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.alpha_model_validation import (
    DEFAULT_OUTPUT_PATH,
    build_alpha_model_validation,
    write_alpha_model_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.3.3 regime alpha model validation.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20991231")
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_alpha_model_validation(
        start_date=args.start,
        end_date=args.end,
        step_sessions=args.step,
    )
    output = write_alpha_model_validation(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "score_date_count": payload["metadata"]["score_date_count"],
                "score_start": payload["metadata"]["score_start"],
                "score_end": payload["metadata"]["score_end"],
                "regime_counts": payload["summary"]["score_date_regime_counts"],
                "router_selected_tradable": payload["tradable_etf_validation"]["router_selected"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
