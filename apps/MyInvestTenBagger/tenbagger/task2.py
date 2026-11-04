"""TASK 2 orchestration."""

from __future__ import annotations

from pathlib import Path

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.factor_engine import FactorEngine
from tenbagger.factor_storage import FactorStorage, build_task2_report
from tenbagger.universe import UniverseManager


def run_task2(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict:
    universe = UniverseManager().resolve(universe_level)
    engine = FactorEngine()
    task1_data = engine.read_task1_parquet(data_dir, universe=universe.codes)
    factors = engine.compute(task1_data)
    validation = engine.validate(factors)

    if validation.future_leak_rows:
        raise RuntimeError(f"Factor validation failed: {validation.future_leak_rows} future leak rows.")
    if validation.nan_cells:
        raise RuntimeError(f"Factor validation failed: {validation.nan_cells} NaN score cells.")
    if validation.score_std <= 0:
        raise RuntimeError("Factor validation failed: tenbagger score distribution is flat.")

    storage = FactorStorage(data_dir).write(factors)
    return build_task2_report(factors, validation, storage, report_dir, universe=universe.to_api())
