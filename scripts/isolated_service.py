"""Test-only service entry point with external socket connections blocked."""
import runpy
import sys
from pathlib import Path

import offline_tests

offline_tests.pytest_configure(None)
args = sys.argv[1:]
sys.path.insert(0, str(Path.cwd()))
if args[0] == "-m":
    sys.argv = args[1:]
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
else:
    sys.argv = args
    sys.path.insert(0, str(Path(args[0]).resolve().parent))
    runpy.run_path(args[0], run_name="__main__")
