"""B2 Slice 2A: assert src/correlator/ is covered by the Path-C
AST import-topology scan.

The guard lives in ``tests/test_path_c_import_topology.py``. It
iterates ``_PATH_C_ROOTS`` plus ``_PATH_C_FILES``. This test asserts
that ``src/correlator/`` is in the scan's roots — so any future
Path-C-forbidden construct (uuid4, datetime.now, data/cases access,
evaluation import, etc.) introduced under ``src/correlator/`` will
be caught by CI.

Failure modes this guards against:
  - someone renames / moves the correlator and forgets to update
    the scan roots;
  - someone adds a new path (e.g. ``src/correlator/engine/``) that
    becomes a silent blind spot if the scan only covers the top
    module.
"""

from __future__ import annotations

import importlib
import os
import sys

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS_DIR = os.path.join(_PROJECT_DIR, "tests")
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)


def test_correlator_root_is_in_scan_roots():
    mod = importlib.import_module("test_path_c_import_topology")
    roots = list(getattr(mod, "_PATH_C_ROOTS"))
    expected = os.path.join(_PROJECT_DIR, "src", "correlator")
    assert expected in roots, (
        f"src/correlator/ missing from _PATH_C_ROOTS. "
        f"got={roots!r}"
    )


def test_correlator_directory_exists():
    expected = os.path.join(_PROJECT_DIR, "src", "correlator")
    assert os.path.isdir(expected), expected


def test_scan_picks_up_correlator_files():
    # The scan's _iter_py_files walks every root. It must yield at
    # least one file under src/correlator/.
    mod = importlib.import_module("test_path_c_import_topology")
    files = list(mod._iter_py_files())
    correlator_files = [
        f for f in files
        if os.sep + "correlator" + os.sep in f
    ]
    assert correlator_files, (
        f"AST scan did not pick up any src/correlator/ files. "
        f"all_files_count={len(files)}"
    )
