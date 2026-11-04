from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the TenBagger web dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    from tenbagger.web_app import create_app

    uvicorn.run(
        create_app(report_dir=Path(args.report_dir)),
        host=args.host,
        port=args.port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
