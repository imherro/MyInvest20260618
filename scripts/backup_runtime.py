"""Consistent local database backups before switching the unified runtime."""
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASES = {
    "MyInvestETF": "data/local/myinvestetf.sqlite",
    "MyInvestStock": "data/local/myinveststock.sqlite",
    "MyInvestShadow": "data/shadow_account.sqlite",
    "MyShortTerm": "data/shortterm.sqlite",
}


def main():
    destination = ROOT / "runtime/backups" / time.strftime("%Y%m%d_%H%M%S")
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for directory, relative in DATABASES.items():
        source = ROOT.parent / directory / relative
        target = destination / directory / Path(relative).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as reader, sqlite3.connect(target) as writer:
            reader.backup(writer)
            integrity = writer.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"Backup integrity failed: {directory}")
        records.append({"system": directory, "source": str(source), "backup": str(target), "bytes": target.stat().st_size, "quick_check": integrity})
    (destination / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Verified {len(records)} database backups: {destination}")


if __name__ == "__main__":
    main()
