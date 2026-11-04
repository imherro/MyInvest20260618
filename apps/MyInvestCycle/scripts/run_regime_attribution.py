from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from core.alpha_decomposition_engine import build_alpha_decomposition
from core.regime_performance_attribution import (
    DEFAULT_SHADOW_BACKTEST_PATH,
    build_regime_performance_attribution,
    load_shadow_backtest,
)


DEFAULT_OUTPUT = DATA_DIR / "regime_performance_attribution.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run S1.2 regime-based performance attribution.")
    parser.add_argument("--start", default=None, help="Optional start date, YYYYMMDD.")
    parser.add_argument("--end", default=None, help="Optional end date, YYYYMMDD.")
    parser.add_argument("--input", default=str(DEFAULT_SHADOW_BACKTEST_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shadow_backtest = load_shadow_backtest(args.input)
    attribution = build_regime_performance_attribution(
        shadow_backtest,
        start_date=args.start,
        end_date=args.end,
    )
    attribution["alpha_decomposition"] = build_alpha_decomposition(attribution)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(attribution, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "summary": attribution["summary"],
                "alpha_decomposition": attribution["alpha_decomposition"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
