"""Phase 0: outcome_store.summary() carries schema_version="1.0"."""

import os
import sys

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from outcome_store import OutcomeStore


def test_empty_summary_has_schema_version():
    assert OutcomeStore().summary()["schema_version"] == "1.0"


def test_schema_version_is_top_level_key():
    summary = OutcomeStore().summary()
    assert "schema_version" in summary
    assert summary["schema_version"] == "1.0"
