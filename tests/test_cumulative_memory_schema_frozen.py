"""B3 Slice 2A: CumulativeMemoryConfig contract freeze.

Focused invariants for the B3 cumulative-memory module. Mirrors
``tests/test_replan_schema_frozen.py`` and
``tests/test_correlator_schema_frozen.py``:

  - Closed ``CUMULATIVE_MEMORY_DEDUPE_POLICY`` Literal (Slice 2A
    admits exactly ``"drop_equal_raise_mismatch"``).
  - ``KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES`` matches the
    Literal set exactly.
  - ``MAX_CUMULATIVE_MEMORY_RECORDS`` is a positive int and
    matches the registered 1.0 constant value.
  - ``CumulativeMemoryConfig`` default construction is runtime-
    no-op safe (empty ``prior_session_refs``, default cap,
    default policy).
  - ``CumulativeMemoryConfig`` field set is exactly the expected
    set — no silent field drift.
  - ``__post_init__`` rejects bad values
    (empty-string refs, non-string refs, unknown policy,
    out-of-range cap, wrong schema_version).
  - ``prior_session_refs`` normalizes iterable inputs to a
    ``tuple``.
  - ``CumulativeMemoryCollisionError`` is a ``ValueError``
    subclass (dedupe-rule collisions are value errors, not
    runtime type errors).
  - ``load_cumulative_memory`` is a signature-only stub in Slice
    2A — it raises ``NotImplementedError`` on call. Invoking it
    in Slice 2A is a test-time proof that no runtime loader body
    has been merged by accident.
  - ``CUMULATIVE_MEMORY_SCHEMA_VERSION`` pinned at ``"1.0"`` and
    matches the ``CumulativeMemoryConfig`` default.

No runtime memory loading is exercised — the point is to freeze
the shape before Slice 2B's body lands.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import typing

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from learning.cumulative_memory import (  # noqa: E402
    CUMULATIVE_MEMORY_DEDUPE_POLICY,
    CUMULATIVE_MEMORY_SCHEMA_VERSION,
    CumulativeMemoryCollisionError,
    CumulativeMemoryConfig,
    CumulativeMemorySourceResolver,
    KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES,
    MAX_CUMULATIVE_MEMORY_RECORDS,
    load_cumulative_memory,
)
from learning.memory_schema import MemoryRecord  # noqa: E402


def _empty_resolver(_ref: str) -> list[MemoryRecord]:
    """Sentinel resolver used only to satisfy the required kwarg in
    Slice 2A stub-tests — the loader body is still a
    ``NotImplementedError`` so this resolver is never invoked."""
    return []


# ---------------------------------------------------------------------------
# Closed Literal + known-values registry
# ---------------------------------------------------------------------------


def test_dedupe_policy_literal_is_closed_single_value():
    args = typing.get_args(CUMULATIVE_MEMORY_DEDUPE_POLICY)
    assert args == ("drop_equal_raise_mismatch",), (
        "D1 dedupe policy must be a closed single-value Literal in "
        f"Slice 2A, got {args!r}"
    )


def test_known_dedupe_policies_matches_literal_exactly():
    literal_args = set(typing.get_args(CUMULATIVE_MEMORY_DEDUPE_POLICY))
    assert KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES == literal_args, (
        "KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES drifted from the "
        "closed Literal"
    )
    assert isinstance(KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES, frozenset)


def test_known_dedupe_policies_entries_are_non_empty_strings():
    for policy in KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES:
        assert isinstance(policy, str) and policy.strip(), policy


# ---------------------------------------------------------------------------
# MAX_CUMULATIVE_MEMORY_RECORDS
# ---------------------------------------------------------------------------


def test_max_cumulative_memory_records_is_positive_int():
    assert isinstance(MAX_CUMULATIVE_MEMORY_RECORDS, int)
    assert not isinstance(MAX_CUMULATIVE_MEMORY_RECORDS, bool)
    assert MAX_CUMULATIVE_MEMORY_RECORDS >= 1


def test_max_cumulative_memory_records_is_registered_value():
    # The registry entry documents 1000 as the suggested value;
    # lock it here so a silent change trips a test.
    assert MAX_CUMULATIVE_MEMORY_RECORDS == 1000


# ---------------------------------------------------------------------------
# CumulativeMemoryCollisionError type
# ---------------------------------------------------------------------------


def test_collision_error_is_value_error_subclass():
    assert issubclass(CumulativeMemoryCollisionError, ValueError)


# ---------------------------------------------------------------------------
# CumulativeMemoryConfig: field set + defaults
# ---------------------------------------------------------------------------


def test_cumulative_memory_config_is_frozen_dataclass():
    assert dataclasses.is_dataclass(CumulativeMemoryConfig)
    params = getattr(CumulativeMemoryConfig, "__dataclass_params__", None)
    assert params is not None
    assert params.frozen is True, (
        "CumulativeMemoryConfig must be a FROZEN dataclass to prevent "
        "post-construction mutation"
    )


def test_cumulative_memory_config_field_set_is_exact():
    expected = {
        "prior_session_refs",
        "dedupe_policy",
        "max_records",
        "schema_version",
    }
    actual = {f.name for f in dataclasses.fields(CumulativeMemoryConfig)}
    assert actual == expected, (
        f"CumulativeMemoryConfig field set drifted. "
        f"missing={expected - actual}, unexpected={actual - expected}"
    )


def test_cumulative_memory_config_has_no_filesystem_path_field():
    """Planner-locked: no ``prior_session_dirs`` (filesystem paths)
    on the canonical config surface. Paths are a CLI-layer concern
    only — they must never enter the digest-contributing config."""
    fields = {f.name for f in dataclasses.fields(CumulativeMemoryConfig)}
    for forbidden in ("prior_session_dirs", "paths", "prior_paths"):
        assert forbidden not in fields, (
            f"CumulativeMemoryConfig must not carry raw filesystem "
            f"paths — {forbidden!r} is a D5-forbidden field"
        )


def test_cumulative_memory_config_defaults_are_runtime_no_op():
    cfg = CumulativeMemoryConfig()
    assert cfg.prior_session_refs == tuple()
    assert cfg.dedupe_policy == "drop_equal_raise_mismatch"
    assert cfg.max_records == MAX_CUMULATIVE_MEMORY_RECORDS
    assert cfg.schema_version == CUMULATIVE_MEMORY_SCHEMA_VERSION


def test_cumulative_memory_config_accepts_valid_refs():
    cfg = CumulativeMemoryConfig(
        prior_session_refs=("sess_abc", "sess_def"),
        max_records=10,
    )
    assert cfg.prior_session_refs == ("sess_abc", "sess_def")
    assert cfg.max_records == 10


def test_cumulative_memory_config_normalizes_list_to_tuple():
    cfg = CumulativeMemoryConfig(prior_session_refs=["sess_a", "sess_b"])
    assert isinstance(cfg.prior_session_refs, tuple)
    assert cfg.prior_session_refs == ("sess_a", "sess_b")


# ---------------------------------------------------------------------------
# __post_init__ validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        # prior_session_refs must be strings
        ({"prior_session_refs": ("sess_a", 123)}, TypeError),
        # prior_session_refs must be non-empty strings
        ({"prior_session_refs": ("sess_a", "")}, ValueError),
        ({"prior_session_refs": ("sess_a", "   ")}, ValueError),
        # dedupe_policy must be in closed set
        ({"dedupe_policy": "overwrite"}, ValueError),
        ({"dedupe_policy": ""}, ValueError),
        # max_records must be int
        ({"max_records": "10"}, TypeError),
        ({"max_records": True}, TypeError),
        # max_records must be in range
        ({"max_records": 0}, ValueError),
        ({"max_records": -1}, ValueError),
        ({"max_records": MAX_CUMULATIVE_MEMORY_RECORDS + 1}, ValueError),
        # schema_version must be pinned
        ({"schema_version": "2.0"}, ValueError),
        ({"schema_version": "1.1"}, ValueError),
    ],
)
def test_cumulative_memory_config_validator_rejects_bad_values(kwargs, exc):
    with pytest.raises(exc):
        CumulativeMemoryConfig(**kwargs)


def test_cumulative_memory_config_rejects_non_iterable_refs():
    with pytest.raises(TypeError):
        CumulativeMemoryConfig(prior_session_refs=42)  # type: ignore[arg-type]


def test_cumulative_memory_config_accepts_empty_tuple_of_refs():
    # Empty is legal — loader will return an empty EpisodicMemory.
    cfg = CumulativeMemoryConfig(prior_session_refs=())
    assert cfg.prior_session_refs == ()


# ---------------------------------------------------------------------------
# Loader signature — Slice 2A: body must raise NotImplementedError
# ---------------------------------------------------------------------------


def test_load_cumulative_memory_empty_config_returns_empty_memory():
    """Slice 2B pin: calling the loader with an empty config no
    longer raises ``NotImplementedError`` — it returns a fresh,
    empty ``EpisodicMemory`` and must not invoke the resolver."""
    cfg = CumulativeMemoryConfig()
    calls: list[str] = []

    def tracking_resolver(ref: str) -> list[MemoryRecord]:
        calls.append(ref)
        return []

    mem = load_cumulative_memory(cfg, source_resolver=tracking_resolver)
    from learning.episodic_memory import EpisodicMemory

    assert isinstance(mem, EpisodicMemory)
    assert len(mem) == 0
    assert calls == [], (
        "source_resolver must not be invoked when "
        "prior_session_refs is empty"
    )


def test_load_cumulative_memory_signature_is_config_plus_kwonly_resolver():
    """D10 pin: the loader signature is
    ``(config, *, source_resolver) -> EpisodicMemory``.
    ``source_resolver`` must be keyword-only and required."""
    import inspect

    sig = inspect.signature(load_cumulative_memory)
    params = list(sig.parameters.values())
    assert len(params) == 2, (
        "load_cumulative_memory must take exactly two parameters "
        f"(config + kwarg-only source_resolver), got {len(params)}"
    )
    config_param, resolver_param = params
    assert config_param.name == "config"
    assert config_param.kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert resolver_param.name == "source_resolver"
    assert resolver_param.kind is inspect.Parameter.KEYWORD_ONLY, (
        "source_resolver must be keyword-only (per D10) — received "
        f"{resolver_param.kind.name}"
    )
    assert resolver_param.default is inspect.Parameter.empty, (
        "source_resolver must have no default (required per D10); "
        f"default={resolver_param.default!r}"
    )


def test_load_cumulative_memory_rejects_missing_source_resolver():
    """D10 pin: calling the loader without supplying
    ``source_resolver`` must raise ``TypeError`` (argparse-style),
    not silently proceed with some implicit lookup."""
    cfg = CumulativeMemoryConfig()
    with pytest.raises(TypeError):
        load_cumulative_memory(cfg)  # type: ignore[call-arg]


def test_source_resolver_type_alias_is_exported():
    """The ``CumulativeMemorySourceResolver`` type alias is part
    of the public surface — callers build resolvers against it
    for type clarity."""
    import typing

    origin = typing.get_origin(CumulativeMemorySourceResolver)
    args = typing.get_args(CumulativeMemorySourceResolver)
    # Callable[[str], list[MemoryRecord]] → origin is
    # collections.abc.Callable; args are (parameter types tuple, return type)
    # in typing's representation.
    import collections.abc

    assert origin is collections.abc.Callable, (
        f"CumulativeMemorySourceResolver must be a Callable type "
        f"alias, got origin={origin!r}"
    )
    # args is ([str], list[MemoryRecord]) in typing's flattened form.
    param_types = args[0]
    return_type = args[-1]
    assert list(param_types) == [str], (
        f"resolver must accept a single str ref, got {param_types!r}"
    )
    # return type is list[MemoryRecord]
    assert typing.get_origin(return_type) is list
    (inner,) = typing.get_args(return_type)
    assert inner is MemoryRecord, (
        f"resolver must return list[MemoryRecord], got list[{inner!r}]"
    )


# ---------------------------------------------------------------------------
# Version pin
# ---------------------------------------------------------------------------


def test_cumulative_memory_schema_version_pin():
    assert CUMULATIVE_MEMORY_SCHEMA_VERSION == "1.0"
    assert CumulativeMemoryConfig().schema_version == "1.0"
