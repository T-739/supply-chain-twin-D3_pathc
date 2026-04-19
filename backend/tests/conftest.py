"""B5 backend test fixtures.

Uses the shared fixture bundle builder to synthesize a throwaway
``bundles/`` directory in a tmp_path per test — we deliberately
do NOT point tests at the committed fixture directory under
``<repo>/bundles/`` so the tests don't accidentally couple to
bytes that might legitimately be regenerated.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.bundler.fixture_builder import (  # noqa: E402
    build_b4_triplet_fixture,
    build_default_3mode_fixture,
)


@pytest.fixture
def bundles_root_with_default(tmp_path) -> str:
    bundles_root = tmp_path / "bundles"
    build_default_3mode_fixture(str(bundles_root))
    return str(bundles_root)


@pytest.fixture
def bundles_root_with_b4(tmp_path) -> str:
    bundles_root = tmp_path / "bundles"
    build_b4_triplet_fixture(str(bundles_root))
    return str(bundles_root)


@pytest.fixture
def bundles_root_with_both(tmp_path) -> str:
    bundles_root = tmp_path / "bundles"
    build_default_3mode_fixture(str(bundles_root))
    build_b4_triplet_fixture(str(bundles_root))
    return str(bundles_root)
