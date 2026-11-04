"""Run monorepo code with explicitly verified legacy data and environment."""
import argparse
import os
import runpy
import sys
from pathlib import Path

from subsystems import ROOT, systems


def runtime_paths(system, root=ROOT):
    source = root / "apps" / system["directory"]
    legacy = root.parent / system["directory"]
    return [(source / relative, legacy / relative) for relative in system["runtime_paths"]]


def validate_runtime(system, root=ROOT):
    for mount, original in runtime_paths(system, root):
        if not original.is_dir() or not mount.is_dir() or mount.resolve() != original.resolve():
            raise RuntimeError(f"Runtime binding missing or incorrect: {mount}; run prepare_runtime.ps1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, choices=[s["id"] for s in systems()])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--layout", choices=["monorepo", "legacy"], default="monorepo")
    args = parser.parse_args()
    system = next(s for s in systems() if s["id"] == args.system)
    legacy = ROOT.parent / system["directory"]
    source = ROOT / "apps" / system["directory"] if args.layout == "monorepo" else legacy
    if args.layout == "monorepo":
        validate_runtime(system)
    env_file = legacy / ".env"
    if not env_file.is_file():
        raise RuntimeError(f"Original environment file missing: {env_file}")
    from dotenv import load_dotenv
    load_dotenv(env_file, encoding="utf-8-sig", override=False)
    os.environ["MYINVEST_ENV_FILE"] = str(env_file)
    if system["id"] == "market":
        os.environ["MYINVEST_MARKET_WEB_DATA"] = str(legacy / "web/data")
    os.environ.pop("PYTHONPATH", None)
    os.chdir(source)
    sys.path.insert(0, str(source))
    command = [*system["command"], "--host", args.host, "--port", str(system["port"])]
    print(f"system={args.system} layout={args.layout} source={source} port={system['port']}", flush=True)
    if command[0] == "-m":
        sys.argv = command[1:]
        runpy.run_module(command[1], run_name="__main__", alter_sys=True)
    else:
        entry = source / command[0]
        sys.path.insert(0, str(entry.parent))
        sys.argv = [str(entry), *command[1:]]
        runpy.run_path(str(entry), run_name="__main__")


if __name__ == "__main__":
    main()
