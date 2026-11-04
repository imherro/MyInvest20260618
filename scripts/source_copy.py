"""Copy tracked source only, never follow production runtime junctions."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_files(directory):
    prefix = f"apps/{directory}/"
    result = subprocess.check_output(["git", "ls-files", "-z", "--", prefix], cwd=ROOT)
    return [ROOT / name for name in result.decode("utf-8").split("\0") if name]


def copy_source(directory, destination):
    source = ROOT / "apps" / directory
    destination.mkdir(parents=True, exist_ok=True)
    for path in source_files(directory):
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Tracked source resolves outside application: {path}")
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
