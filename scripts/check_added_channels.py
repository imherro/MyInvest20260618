"""Read-only acceptance of TAA detail pages and existing Test research artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8888")
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.origin.startswith("http://127.0.0.1:"):
        parser.error("Use a loopback origin for data-preservation checks")
    opener = build_opener(ProxyHandler({}))
    results = []

    def read(path):
        row = {"path": path}
        try:
            with opener.open(args.origin + path, timeout=30) as response:
                body = response.read()
                row.update(status=response.status, bytes=len(body))
                results.append(row)
                return body
        except Exception as exc:
            row.update(status=0, error=type(exc).__name__)
            results.append(row)
            return b"{}"

    for path in ["/", "/allocation", "/research", "/shadow", "/data", "/site-map",
                 "/strategies", "/strategies/current-taa", "/strategies/p2-style-drawdown"]:
        read("/taa" + path)
    taa = json.loads(read("/api/taa/index"))
    root = args.originals / "MyInvestTAA/reports/current"
    expected = {name: json.loads((root / (name + ".json")).read_text(encoding="utf-8"))
                for name in ["allocation", "data_status", "manifest", "research", "shadow"]}
    results.append({"test": "taa_report_values_preserved", "status": 200 if taa.get("reports") == expected else 500,
                    "basis_date": taa.get("basis_date")})
    index = json.loads(read("/api/test/index"))
    output = (args.originals / "MyInvestTest/output").resolve()
    for artifact in index.get("artifacts", []):
        name = artifact["name"]
        source = (output / name).resolve()
        if source.parent != output or not source.is_file():
            raise ValueError("Invalid artifact source path")
        body = read(artifact["url"])
        if source.suffix in {".csv", ".json", ".md"}:
            results.append({"test": "download_bytes_preserved", "name": name,
                            "status": 200 if hashlib.sha256(body).digest() == hashlib.sha256(source.read_bytes()).digest() else 500})
    results.append({"test": "research_artifacts_present", "status": 200 if index.get("artifacts") else 500,
                    "basis_date": index.get("basis_date")})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"checks": len(results), "failures": [r for r in results if r["status"] != 200], "evidence": str(args.output)}))
    return int(any(r["status"] != 200 for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
