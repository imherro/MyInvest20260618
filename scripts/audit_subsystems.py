"""Audit source provenance and detect local credential values without printing them."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from import_subsystems import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, default=ROOT.parent)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/migration/source-snapshot.json").read_text(encoding="utf-8"))
    values = set()
    changed_originals, adaptations, missing = [], [], []
    for project in manifest["projects"]:
        name = project["directory"]
        env_path = args.originals / name / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                value = value.strip().strip('"\'')
                if sep and re.search(r"TOKEN|SECRET|KEY|PASSWORD", key, re.I) and len(value) >= 16:
                    values.add(value.encode())
        for entry in project["files"]:
            relative = f"apps/{name}/{entry['path']}"
            original = args.originals / name / entry["path"]
            imported = ROOT / relative
            if not original.exists() or hashlib.sha256(original.read_bytes()).hexdigest() != entry["sha256"]:
                changed_originals.append(f"{name}/{entry['path']}")
            if not imported.exists():
                missing.append(relative)
            elif hashlib.sha256(imported.read_bytes()).hexdigest() != entry["sha256"]:
                adaptations.append(relative)
    findings = []
    for path in (ROOT / "apps").rglob("*"):
        if not path.is_file() or any(p in {"__pycache__", ".pytest_cache"} for p in path.parts):
            continue
        content = path.read_bytes()
        if any(value in content for value in values) or re.search(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)", content):
            findings.append(path.relative_to(ROOT).as_posix())
    result = {"original_source_changes": changed_originals, "missing_imports": missing,
              "adaptations": adaptations, "credential_match_files": findings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(changed_originals or missing or findings))


if __name__ == "__main__":
    raise SystemExit(main())
