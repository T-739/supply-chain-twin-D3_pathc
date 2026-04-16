"""Test-only shim for invoking scripts/batch_eval_runner.py helpers.

Keeps the runner itself minimal while letting tests call build_rows against
both real case IDs and synthetic fixture cases (for skip-path coverage).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Iterable

_PROJECT_DIR = Path(__file__).parent.parent

# Load scripts/batch_eval_runner.py as a module (it is not a package).
_spec = importlib.util.spec_from_file_location(
    "batch_eval_runner",
    _PROJECT_DIR / "scripts" / "batch_eval_runner.py",
)
batch_eval_runner = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules.setdefault("batch_eval_runner", batch_eval_runner)
_spec.loader.exec_module(batch_eval_runner)  # type: ignore[union-attr]


def batch_override_rows(case_ids: Iterable[str]) -> list[dict]:
    """Run the real override batch against real case files."""
    return batch_eval_runner.build_rows("override", list(case_ids))


def batch_rows_with_fixture_cases(
    mode: str,
    fixtures: dict[str, dict],
    tmp_path: Path,
) -> list[dict]:
    """Run the batch runner with an in-memory set of synthetic cases.

    We monkey-patch `_load_case` to return the fixture dict instead of
    reading from disk, without touching the runner's source.
    """
    original_loader = batch_eval_runner._load_case

    def _fixture_loader(case_id: str):
        return fixtures.get(case_id)

    batch_eval_runner._load_case = _fixture_loader
    try:
        return batch_eval_runner.build_rows(mode, list(fixtures.keys()))
    finally:
        batch_eval_runner._load_case = original_loader
