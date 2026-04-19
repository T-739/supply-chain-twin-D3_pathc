"""Phase 1: JSONL append-only store tests."""

from __future__ import annotations

import json
import os
import sys

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from outcome_persistence.jsonl_store import JSONLStore


def test_append_then_read_preserves_order(tmp_path):
    store = JSONLStore(tmp_path / "mem.jsonl")
    store.append({"k": 1, "event_id": "A"})
    store.append({"k": 2, "event_id": "B"})
    store.append({"k": 3, "event_id": "C"})
    assert store.read_all() == [
        {"k": 1, "event_id": "A"},
        {"k": 2, "event_id": "B"},
        {"k": 3, "event_id": "C"},
    ]


def test_each_line_independently_loadable(tmp_path):
    path = tmp_path / "mem.jsonl"
    store = JSONLStore(path)
    store.append({"a": 1})
    store.append({"b": 2})

    with open(path, "r") as f:
        lines = [ln for ln in f.read().split("\n") if ln]

    assert [json.loads(ln) for ln in lines] == [{"a": 1}, {"b": 2}]


def test_canonical_form_is_sorted_keys(tmp_path):
    path = tmp_path / "mem.jsonl"
    store = JSONLStore(path)
    store.append({"z": 1, "a": 2, "m": 3})

    with open(path, "r") as f:
        line = f.read().rstrip("\n")

    # Sorted keys, compact separators.
    assert line == '{"a":2,"m":3,"z":1}'


def test_crash_tolerance_preserves_prior_complete_lines(tmp_path):
    path = tmp_path / "mem.jsonl"
    store = JSONLStore(path)
    store.append({"row": 0})
    store.append({"row": 1})

    # Simulate a mid-write crash: append a partial (non-JSON) trailing fragment.
    with open(path, "a") as f:
        f.write('{"row": 2, "pa')  # no closing brace, no newline
        f.flush()

    rows = store.read_all()
    assert rows == [{"row": 0}, {"row": 1}]


def test_read_empty_file(tmp_path):
    path = tmp_path / "mem.jsonl"
    open(path, "a").close()
    assert JSONLStore(path).read_all() == []


def test_read_missing_file_returns_empty(tmp_path):
    assert JSONLStore(tmp_path / "never_written.jsonl").read_all() == []


def test_write_all_overwrites(tmp_path):
    path = tmp_path / "mem.jsonl"
    store = JSONLStore(path)
    store.append({"row": 0})
    store.write_all([{"row": 10}, {"row": 11}])
    assert store.read_all() == [{"row": 10}, {"row": 11}]
