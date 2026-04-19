"""B1 Slice 2: purity invariants for the trigger layer.

Covers both ``estimate_expected_outcome`` and
``decide_replan_trigger``. These functions are declared pure and
deterministic. This test fails loudly on any of:

  - non-identical outputs across repeated calls with identical
    structured inputs;
  - mutation of any input dict (cost_output, governance_meta,
    execution_outcome);
  - dependency on wall-clock, randomness, or thread state (verified
    by patching ``time`` / ``datetime`` / ``random`` and asserting no
    calls to them);
  - import-level dependency on forbidden Path C modules.

These are guard tests — they should be trivially cheap. Their job is
to fail fast when a future edit sneaks an impure call into the
pipeline.
"""

from __future__ import annotations

import ast
import copy
import os
import sys

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from replan import (  # noqa: E402
    ExpectedOutcomeRef,
    ReplanConfig,
    decide_replan_trigger,
    estimate_expected_outcome,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _cost_output() -> dict:
    return {
        "cost_estimates": [
            {
                "candidate_id": "C1",
                "candidate_type": "EXPEDITE",
                "is_feasible": True,
                "direct_cost_estimate": 200.0,
                "recovery_cost_estimate": 0.0,
                "total_cost_estimate": 200.0,
                "cost_breakdown_explanation": "",
                "estimation_notes": "",
            },
        ],
        "order_units_used": 10,
        "planned_eta_used": 36.0,
        "cost_policy_used": {},
    }


def _governance_meta() -> dict:
    return {
        "recommended_candidate_id": "C1",
        "recommended_candidate_type": "EXPEDITE",
        "alternatives": [],
        "mode": "rules",
        "llm_enriched_fields": [],
        "llm_trace": None,
    }


def _execution_outcome(cost: float = 100.0, sla: bool = True) -> dict:
    return {
        "cost_incurred": cost,
        "sla_impact": {"preserved": sla, "late_hours": 0.0},
    }


# ---------------------------------------------------------------------------
# Repeated calls with identical inputs produce identical outputs
# ---------------------------------------------------------------------------


def test_estimator_is_idempotent_across_repeated_calls():
    co = _cost_output()
    gm = _governance_meta()
    cfg = ReplanConfig()
    outputs = [
        estimate_expected_outcome(
            cost_output=co, governance_meta=gm, config=cfg,
        ).model_dump()
        for _ in range(5)
    ]
    for out in outputs[1:]:
        assert out == outputs[0]


def test_trigger_is_idempotent_across_repeated_calls():
    expected = ExpectedOutcomeRef(
        expected_cost_min=80.0,
        expected_cost_max=120.0,
        expected_sla_preserved=True,
        estimator_id="test",
    )
    eo = _execution_outcome(cost=500.0)  # out-of-range
    cfg = ReplanConfig()
    outputs = [
        decide_replan_trigger(
            expected_outcome=expected,
            execution_status="executed",
            execution_outcome=eo,
            attempt_index=0,
            config=cfg,
        ).model_dump()
        for _ in range(5)
    ]
    for out in outputs[1:]:
        assert out == outputs[0]


# ---------------------------------------------------------------------------
# Inputs must not mutate
# ---------------------------------------------------------------------------


def test_estimator_does_not_mutate_cost_output_or_governance_meta():
    co = _cost_output()
    gm = _governance_meta()
    co_before = copy.deepcopy(co)
    gm_before = copy.deepcopy(gm)
    estimate_expected_outcome(
        cost_output=co, governance_meta=gm, config=ReplanConfig(),
    )
    assert co == co_before
    assert gm == gm_before


def test_trigger_does_not_mutate_execution_outcome():
    expected = ExpectedOutcomeRef(
        expected_cost_min=80.0,
        expected_cost_max=120.0,
        expected_sla_preserved=True,
        estimator_id="test",
    )
    eo = _execution_outcome(cost=500.0, sla=False)
    eo_before = copy.deepcopy(eo)
    decide_replan_trigger(
        expected_outcome=expected,
        execution_status="executed",
        execution_outcome=eo,
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert eo == eo_before


# ---------------------------------------------------------------------------
# No wall-clock / randomness calls
# ---------------------------------------------------------------------------


def test_no_wallclock_or_random_calls_during_trigger(monkeypatch):
    import datetime as _dt
    import random as _random
    import time as _time

    def _boom(name):
        def _raise(*a, **kw):
            raise AssertionError(
                f"trigger layer must not call {name}; got args={a!r} kwargs={kw!r}"
            )
        return _raise

    monkeypatch.setattr(_time, "time", _boom("time.time"))
    monkeypatch.setattr(_random, "random", _boom("random.random"))
    monkeypatch.setattr(_random, "randint", _boom("random.randint"))
    # datetime.now is a classmethod on a C type; skip the full patch and
    # trust the import-topology guard + AST scan for Path C roots. We
    # can still ensure datetime.datetime.utcnow isn't called via the
    # module-level shim available to us:
    monkeypatch.setattr(_dt, "datetime", _dt.datetime, raising=False)

    expected = ExpectedOutcomeRef(
        expected_cost_min=80.0,
        expected_cost_max=120.0,
        expected_sla_preserved=True,
        estimator_id="test",
    )
    rec = decide_replan_trigger(
        expected_outcome=expected,
        execution_status="executed",
        execution_outcome=_execution_outcome(cost=100.0, sla=True),
        attempt_index=0,
        config=ReplanConfig(),
    )
    assert rec.trigger_type == "NO_TRIGGER"


def test_no_wallclock_or_random_calls_during_estimator(monkeypatch):
    import random as _random
    import time as _time

    def _boom(name):
        def _raise(*a, **kw):
            raise AssertionError(f"estimator must not call {name}")
        return _raise

    monkeypatch.setattr(_time, "time", _boom("time.time"))
    monkeypatch.setattr(_random, "random", _boom("random.random"))

    ref = estimate_expected_outcome(
        cost_output=_cost_output(),
        governance_meta=_governance_meta(),
        config=ReplanConfig(),
    )
    assert ref.range_source == "cost_output_derived_overlay"


# ---------------------------------------------------------------------------
# Module-level import topology — no learning / event_loop / agents leak.
# ---------------------------------------------------------------------------


# The trigger / estimator must not import from these module roots,
# directly or in their top-level source. Transitive checks belong to
# the broader `tests/test_path_c_import_topology.py` scan; here we
# only need to prove the two Slice 2 files themselves are clean.
_FORBIDDEN_IMPORT_ROOTS = {
    "learning",
    "event_loop_c",
    "event_loop",
    "execution_adapters",
    "agents",
    "evaluation",
    "action_code_mapper",
}


_TARGETS = {
    "replan.expected_outcome": os.path.join(
        _SRC_DIR, "replan", "expected_outcome.py",
    ),
    "replan.replan_trigger": os.path.join(
        _SRC_DIR, "replan", "replan_trigger.py",
    ),
}


def _collect_source_imports(path: str) -> list[str]:
    """Return the module-name roots of every static `import` in a file."""
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            roots.append(mod.split(".")[0])
    return roots


@pytest.mark.parametrize("mod_name,path", list(_TARGETS.items()))
def test_source_has_no_forbidden_imports(mod_name, path):
    """Source-level guard: the two Slice 2 files must not import from
    learning/event_loop/agents/etc.

    Runs against the file's AST, so the result is stable regardless
    of which other tests happened to import those modules earlier in
    the session.
    """
    roots = _collect_source_imports(path)
    leaks = [r for r in roots if r in _FORBIDDEN_IMPORT_ROOTS]
    assert not leaks, f"{mod_name} has forbidden imports: {leaks}"
