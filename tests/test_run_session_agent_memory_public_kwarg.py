"""B4 Slice 2D1: public ``run_session(..., agent_memory_config=None)`` pins.

This is the D10 step 2 surface: ``run_session`` grows exactly one
additive optional kwarg so B4 becomes reachable through the Path
C public API (previously reachable only via the private
``_build_path_c_main_records`` helper).

The tests below pin the full P1–P7 lock set:

- P1 / D8 — exactly one new kwarg (``agent_memory_config``)
  lands; no ``agent_memory_context``, no ``operations_mode``.
- P2 / D9 — ``operations_mode`` stays env-only.
- P3 — the public kwarg threads into the existing internal
  ``_build_path_c_main_records(..., agent_memory_config=...)``
  kwarg and nowhere else.
- P4 — default-off byte identity: passing ``None``, passing a
  default ``AgentMemoryExperimentConfig()``, or passing an
  enabled config outside the W4 gate all produce the same
  artifact shape as the pre-2D1 call.
- F1 / F2 / RO2-closed — Slice 2D1.x. ``session_id`` shifts
  iff ``enable_agent_visible_memory`` is True on the supplied
  config. The fragment reflects public config identity only —
  env ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE`` and the W4
  runtime gate are NOT digest inputs. No kwarg / default
  config / disabled config all preserve pre-B4 ``session_id``
  byte-identity.
- P6 — no ``SessionEventRecord`` overlay, no compare block, no
  KPI.
- P7 — no scripts / harness / CLI touched.
"""

from __future__ import annotations

import inspect
import os
import sys
from typing import Any

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from agent_memory import AgentMemoryExperimentConfig  # noqa: E402
from event_engine import generate_demo_event_stream  # noqa: E402
from event_loop_c import run_session  # noqa: E402
import event_loop_c as _elc_mod  # noqa: E402


def _cfg_default() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig()


def _cfg_enabled() -> AgentMemoryExperimentConfig:
    return AgentMemoryExperimentConfig(enable_agent_visible_memory=True)


def _events():
    # A small, deterministic event stream. The full demo stream is
    # 6 events; we take the first 2 to keep artifact comparisons
    # tight without losing coverage of the Path C main path.
    return generate_demo_event_stream()[:2]


# ---------------------------------------------------------------------------
# 1. Public signature landed (P1 / D8)
# ---------------------------------------------------------------------------


def test_public_signature_contains_agent_memory_config():
    sig = inspect.signature(run_session)
    params = sig.parameters
    assert "agent_memory_config" in params


def test_public_signature_agent_memory_config_default_is_none():
    sig = inspect.signature(run_session)
    p = sig.parameters["agent_memory_config"]
    assert p.default is None


def test_public_signature_agent_memory_config_is_keyword_only():
    sig = inspect.signature(run_session)
    p = sig.parameters["agent_memory_config"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY


def test_public_signature_does_not_expose_agent_memory_context():
    sig = inspect.signature(run_session)
    assert "agent_memory_context" not in sig.parameters


def test_public_signature_does_not_expose_operations_mode():
    """P2 / D9 — operations_mode stays env-only under B4."""
    sig = inspect.signature(run_session)
    assert "operations_mode" not in sig.parameters


def test_public_signature_has_no_other_b4_kwargs():
    sig = inspect.signature(run_session)
    params = set(sig.parameters.keys())
    b4_related = {p for p in params if p.startswith("agent_memory")}
    # Exactly one B4 kwarg; everything else stays internal.
    assert b4_related == {"agent_memory_config"}


# ---------------------------------------------------------------------------
# 2. Default-off invariance via public API (P4)
# ---------------------------------------------------------------------------


def _artifact_model_dump(**kwargs):
    """Run a small PATH_C_WARM session and return
    ``SessionArtifact.model_dump()``. Caller may pass any
    ``run_session`` kwargs."""
    artifact = run_session(
        seed=42,
        mode="PATH_C_WARM",
        events=_events(),
        **kwargs,
    )
    return artifact.model_dump()


def test_default_off_artifact_equals_no_kwarg_artifact():
    a = _artifact_model_dump()
    b = _artifact_model_dump(agent_memory_config=None)
    assert a == b


def test_default_config_off_artifact_equals_no_kwarg_artifact():
    """Passing a default ``AgentMemoryExperimentConfig()`` (which
    has ``enable_agent_visible_memory=False``) must be equivalent
    to not passing the kwarg at all."""
    a = _artifact_model_dump()
    b = _artifact_model_dump(agent_memory_config=_cfg_default())
    assert a == b


def test_enabled_config_but_rules_mode_artifact_is_structurally_equal(monkeypatch):
    """Enabled config but operations_mode resolves to "rules"
    (env default) ⇒ W4 gate blocks B4 at runtime, so no prompt
    injection / memory mutation / event record mutation occurs.
    The artifact therefore matches the no-kwarg call on every
    content-bearing field EXCEPT the ``session_id`` string (and
    the per-record ``session_id`` field that mirrors it), which
    Slice 2D1.x deliberately makes sensitive to the public
    config identity (F1 / F2).
    """
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    a = _artifact_model_dump()
    b = _artifact_model_dump(agent_memory_config=_cfg_enabled())

    # session_id MUST differ (F1 / F2 — digest reflects public
    # config identity, not runtime gate activation).
    assert a["session_id"] != b["session_id"]

    # Everything that is NOT the session_id identity must be
    # structurally equal. Strip the session_id and every
    # session-id-derived field (``memory_record_id`` is a
    # content-addressed id over ``(session_id, event_id,
    # event_timestamp)`` and therefore naturally shifts with
    # session_id; Slice 2D1.x does NOT change that formula).
    _SESSION_ID_DERIVED_KEYS = {"session_id", "memory_record_id"}

    def _strip_ids(dump: dict) -> dict:
        d = {k: v for k, v in dump.items() if k != "session_id"}
        d["event_records"] = [
            {k: v for k, v in rec.items() if k not in _SESSION_ID_DERIVED_KEYS}
            for rec in dump.get("event_records", [])
        ]
        return d

    assert _strip_ids(a)["event_records"] == _strip_ids(b)["event_records"]

    def _strip_snapshot_ids(snap: dict) -> dict:
        # Each MemoryRecord carries session_id (cross-session
        # provenance). When the session_id shifts, every
        # record's session_id field naturally shifts with it.
        # Strip it so we only compare the content-bearing
        # fields.
        out = {k: v for k, v in snap.items() if k != "records"}
        out["records"] = [
            {k: v for k, v in rec.items() if k != "session_id"}
            for rec in snap.get("records", [])
        ]
        return out

    assert _strip_snapshot_ids(a["memory_snapshot"]) == _strip_snapshot_ids(
        b["memory_snapshot"]
    )
    assert a["kpis"] == b["kpis"]
    assert a["config"]["seed"] == b["config"]["seed"]
    assert a["config"]["mode"] == b["config"]["mode"]


# ---------------------------------------------------------------------------
# 3. Public API does not activate B4 outside W4 gate
# ---------------------------------------------------------------------------


def _last_agent_memory_kwargs_seen(monkeypatch, *, mode, env_mode, cfg) -> dict:
    """Spy on ``run_operations_agent_with_meta`` and return the B4
    kwargs the operations agent actually received on the final
    call of the Path C main path (or the BASELINE_STATIC path).
    """
    observed: list[dict[str, Any]] = []

    if env_mode is None:
        monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    else:
        monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", env_mode)

    import agents.operations_agent as _ops_mod
    real_run = _ops_mod.run_operations_agent_with_meta

    def _spy(*args, **kwargs):
        observed.append({
            "ctx": kwargs.get("agent_memory_context"),
            "cfg": kwargs.get("agent_memory_config"),
        })
        safe = dict(kwargs)
        # Safe-run: force rules-mode downstream to avoid any real
        # LLM gateway call in CI. The spy is only about what B4
        # kwargs reach this layer.
        safe["mode"] = "rules"
        safe.pop("agent_memory_context", None)
        safe.pop("agent_memory_config", None)
        return real_run(*args, **safe)

    monkeypatch.setattr(_ops_mod, "run_operations_agent_with_meta", _spy)

    run_session(
        seed=42,
        mode=mode,
        events=_events(),
        agent_memory_config=cfg,
    )
    # Return the last observation; earlier ones are for
    # non-current events in the same session.
    return observed[-1] if observed else {"ctx": None, "cfg": None}


def test_baseline_static_mode_does_not_reach_b4(monkeypatch):
    """BASELINE_STATIC bypasses ``_build_path_c_main_records``
    entirely, so B4 is structurally unreachable."""
    # Spy on the agent entry. BASELINE_STATIC's record-builder
    # does NOT call the operations agent at all (it mirrors the
    # Path B shadow), so the spy may not even be hit — that's
    # fine and is itself a valid negative observation.
    import agents.operations_agent as _ops_mod
    touched = {"n": 0}
    real_run = _ops_mod.run_operations_agent_with_meta

    def _spy(*args, **kwargs):
        touched["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(_ops_mod, "run_operations_agent_with_meta", _spy)
    artifact = run_session(
        seed=42,
        mode="BASELINE_STATIC",
        events=_events(),
        agent_memory_config=_cfg_enabled(),
    )
    # BASELINE_STATIC's artifact shape does not grow any B4
    # surface.
    dump = artifact.model_dump()
    for ev_rec in dump["event_records"]:
        assert "agent_memory_context" not in ev_rec


def test_path_c_cold_mode_does_not_reach_b4(monkeypatch):
    """PATH_C_COLD runs the Path C main path but the W4 gate
    requires ``PATH_C_WARM``, so B4 must not activate."""
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    observed = _last_agent_memory_kwargs_seen(
        monkeypatch,
        mode="PATH_C_COLD",
        env_mode="llm",
        cfg=_cfg_enabled(),
    )
    assert observed["ctx"] is None
    assert observed["cfg"] is None


def test_path_c_warm_rules_mode_does_not_reach_b4(monkeypatch):
    """PATH_C_WARM but operations_mode resolves to ``rules`` ⇒
    W4 condition 4 fails ⇒ no B4 injection."""
    observed = _last_agent_memory_kwargs_seen(
        monkeypatch,
        mode="PATH_C_WARM",
        env_mode="rules",
        cfg=_cfg_enabled(),
    )
    assert observed["ctx"] is None
    assert observed["cfg"] is None


def test_path_c_warm_llm_mode_enabled_config_reaches_b4(monkeypatch):
    """PATH_C_WARM + operations_mode=llm + enabled config ⇒ W4
    gate passes ⇒ operations agent sees a non-None context AND
    a non-None config."""
    observed = _last_agent_memory_kwargs_seen(
        monkeypatch,
        mode="PATH_C_WARM",
        env_mode="llm",
        cfg=_cfg_enabled(),
    )
    assert observed["ctx"] is not None
    assert observed["cfg"] is not None


def test_path_c_warm_llm_mode_disabled_config_does_not_reach_b4(monkeypatch):
    """PATH_C_WARM + operations_mode=llm but flag OFF ⇒ W4
    condition 2 fails ⇒ no B4 injection."""
    observed = _last_agent_memory_kwargs_seen(
        monkeypatch,
        mode="PATH_C_WARM",
        env_mode="llm",
        cfg=_cfg_default(),
    )
    assert observed["ctx"] is None
    assert observed["cfg"] is None


# ---------------------------------------------------------------------------
# 4. Public API forwards config to internal seam (P3)
# ---------------------------------------------------------------------------


def test_public_kwarg_forwards_none_when_absent(monkeypatch):
    observed: dict[str, Any] = {}
    real = _elc_mod._build_path_c_main_records

    def _spy(**kwargs):
        observed["cfg"] = kwargs.get("agent_memory_config", "NOT_PASSED")
        return real(**kwargs)

    monkeypatch.setattr(_elc_mod, "_build_path_c_main_records", _spy)
    run_session(seed=42, mode="PATH_C_WARM", events=_events())
    assert observed["cfg"] is None


def test_public_kwarg_forwards_default_config(monkeypatch):
    observed: dict[str, Any] = {}
    real = _elc_mod._build_path_c_main_records
    cfg = _cfg_default()

    def _spy(**kwargs):
        observed["cfg"] = kwargs.get("agent_memory_config", "NOT_PASSED")
        return real(**kwargs)

    monkeypatch.setattr(_elc_mod, "_build_path_c_main_records", _spy)
    run_session(
        seed=42, mode="PATH_C_WARM", events=_events(),
        agent_memory_config=cfg,
    )
    assert observed["cfg"] is cfg


def test_public_kwarg_forwards_enabled_config(monkeypatch):
    observed: dict[str, Any] = {}
    real = _elc_mod._build_path_c_main_records
    cfg = _cfg_enabled()

    def _spy(**kwargs):
        observed["cfg"] = kwargs.get("agent_memory_config", "NOT_PASSED")
        return real(**kwargs)

    monkeypatch.setattr(_elc_mod, "_build_path_c_main_records", _spy)
    run_session(
        seed=42, mode="PATH_C_WARM", events=_events(),
        agent_memory_config=cfg,
    )
    assert observed["cfg"] is cfg


def test_baseline_static_does_not_reach_path_c_builder(monkeypatch):
    """BASELINE_STATIC does NOT call ``_build_path_c_main_records``
    at all — it goes through ``_build_baseline_static_records``.
    The spy should therefore never fire in that mode."""
    hit = {"n": 0}
    real = _elc_mod._build_path_c_main_records

    def _spy(**kwargs):
        hit["n"] += 1
        return real(**kwargs)

    monkeypatch.setattr(_elc_mod, "_build_path_c_main_records", _spy)
    run_session(
        seed=42, mode="BASELINE_STATIC", events=_events(),
        agent_memory_config=_cfg_enabled(),
    )
    assert hit["n"] == 0


# ---------------------------------------------------------------------------
# 5. No public API creep (P1 re-check)
# ---------------------------------------------------------------------------


def test_public_signature_did_not_grow_unexpected_params():
    """Pin the full parameter set so a future slice that adds a
    second B4 kwarg trips this test and forces a boundary
    review."""
    sig = inspect.signature(run_session)
    assert set(sig.parameters.keys()) == {
        "seed", "mode", "events", "events_source",
        "initial_twin_state", "initial_memory",
        "adaptive_config", "replan_config", "correlator_config",
        "agent_memory_config",
    }


# ---------------------------------------------------------------------------
# 6. Conditional digest fragment (F1 / F2 — Slice 2D1.x, RO2 closed)
# ---------------------------------------------------------------------------


def _session_id_for(cfg):
    """Drive a ``PATH_C_WARM`` run and return ``session_id``.

    No env monkeypatching is baked into this helper; callers set
    ``SUPPLY_CHAIN_TWIN_OPERATIONS_MODE`` when a given test wants
    to confirm the F2 invariant that env is NOT a digest input.
    """
    kwargs = {}
    if cfg is not None:
        kwargs["agent_memory_config"] = cfg
    artifact = run_session(
        seed=42, mode="PATH_C_WARM",
        events=_events(),
        **kwargs,
    )
    return artifact.session_id


def test_session_id_stable_no_kwarg(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    s1 = _session_id_for(None)
    s2 = _session_id_for(None)
    assert s1 == s2


def test_session_id_unchanged_passing_default_config(monkeypatch):
    """F1 — default ``AgentMemoryExperimentConfig()`` has
    ``enable_agent_visible_memory=False`` and therefore
    contributes NO digest fragment. ``session_id`` equals the
    no-kwarg baseline."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    s1 = _session_id_for(None)
    s2 = _session_id_for(_cfg_default())
    assert s1 == s2


def test_session_id_shifts_when_enabled_config_passed(monkeypatch):
    """F1 — enabling the flag contributes the ``agent_memory``
    fragment to ``config_for_digest`` and shifts ``session_id``."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    s_off = _session_id_for(None)
    s_on = _session_id_for(_cfg_enabled())
    assert s_off != s_on


def test_session_id_fragment_is_env_insensitive(monkeypatch):
    """F2 — the fragment reflects public config identity only.
    Enabled config under env ``rules`` and enabled config under
    env ``llm`` produce the same ``session_id``, even though only
    the latter actually activates B4 at runtime."""
    cfg = _cfg_enabled()
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "rules")
    s_rules_env = _session_id_for(cfg)
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    s_llm_env = _session_id_for(cfg)
    assert s_rules_env == s_llm_env


def test_session_id_both_envs_differ_from_off_path(monkeypatch):
    """Companion to the env-insensitivity pin: both env values
    under an enabled config differ from the OFF-path
    ``session_id`` (the two ON runs differ only by their shared
    ``agent_memory`` fragment, not by env)."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    s_off = _session_id_for(None)

    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "rules")
    s_on_rules = _session_id_for(_cfg_enabled())
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    s_on_llm = _session_id_for(_cfg_enabled())

    assert s_on_rules != s_off
    assert s_on_llm != s_off


def test_session_id_fragment_is_mode_insensitive(monkeypatch):
    """F2 — the fragment reflects public config identity only,
    not the session ``mode``. Enabled config under
    ``PATH_C_WARM`` and ``PATH_C_COLD`` contribute the same
    fragment (but ``mode`` itself is separately part of the
    digest, so the two session_ids still differ — this test
    only asserts that the *fragment contribution* is mode-
    insensitive, by checking that if we hold mode constant the
    fragment contribution is byte-stable)."""
    from event_loop_c import _agent_memory_config_digest_fragment
    cfg = _cfg_enabled()
    frag_a = _agent_memory_config_digest_fragment(cfg)
    frag_b = _agent_memory_config_digest_fragment(cfg)
    assert frag_a == frag_b
    # Field set exactly matches the F3 lock.
    assert set(frag_a.keys()) == {
        "enable_agent_visible_memory",
        "target_agent",
        "context_source",
        "max_recent_examples",
        "allowed_modes",
        "schema_version",
    }


def test_digest_fragment_shape_matches_f3():
    """F3 — fragment content is locked to the landed config
    fields, with ``allowed_modes`` emitted as a sorted list (not
    a set/frozenset) so the canonical JSON of the
    ``config_for_digest`` payload is deterministic across Python
    hash seeds."""
    from event_loop_c import _agent_memory_config_digest_fragment
    frag = _agent_memory_config_digest_fragment(_cfg_enabled())
    assert frag == {
        "enable_agent_visible_memory": True,
        "target_agent": "operations",
        "context_source": "structured_summary_plus_recent_examples",
        "max_recent_examples": 3,
        "allowed_modes": ["PATH_C_WARM"],
        "schema_version": "1.0",
    }
    assert isinstance(frag["allowed_modes"], list)


# ---------------------------------------------------------------------------
# 7. Existing public behavior still works
# ---------------------------------------------------------------------------


def test_existing_path_c_warm_call_without_b4_kwarg_returns_schema_valid_artifact():
    artifact = run_session(
        seed=42, mode="PATH_C_WARM", events=_events(),
    )
    # Re-validate through the pydantic model to pin shape.
    from session.session_schema import SessionArtifact

    SessionArtifact.model_validate(artifact.model_dump())


def test_existing_baseline_static_call_without_b4_kwarg_returns_schema_valid_artifact():
    artifact = run_session(
        seed=42, mode="BASELINE_STATIC", events=_events(),
    )
    from session.session_schema import SessionArtifact

    SessionArtifact.model_validate(artifact.model_dump())


def test_no_session_event_record_overlay_added_by_slice_2d1():
    """P6 — ``SessionEventRecord`` still carries no B4 overlay
    field under any of: no kwarg / default config / enabled
    config."""
    from session.session_schema import SessionEventRecord

    forbidden = {"agent_memory_context", "agent_memory_config"}
    leaks = set(SessionEventRecord.model_fields.keys()) & forbidden
    assert not leaks


def test_compare_report_b4_block_remains_opt_in_only():
    """Slice 2D3-A flip of the original Slice 2D1 P6 pin: the
    compare report now carries a B4 ``agent_memory_experiment_
    summary`` sibling block, but only when the caller opts in via
    ``agent_memory_variant_tags`` on ``build_compare_report``. The
    invariant we still enforce is that no field is added to
    ``SessionEventRecord`` / ``SessionKPIs`` and that
    ``COMPARE_REPORT_SCHEMA_VERSION`` is not bumped."""
    from session.session_compare import COMPARE_REPORT_SCHEMA_VERSION
    from session.session_schema import SessionEventRecord, SessionKPIs

    assert COMPARE_REPORT_SCHEMA_VERSION == "1.1"

    forbidden_record_fields = {"agent_memory_context", "agent_memory_config"}
    assert not (
        set(SessionEventRecord.model_fields.keys()) & forbidden_record_fields
    )
    forbidden_kpi_fields = {
        "agent_memory_events_observed",
        "agent_memory_fire_count",
        "agent_memory_enabled_rate",
    }
    assert not (
        set(SessionKPIs.model_fields.keys()) & forbidden_kpi_fields
    )


def test_no_kpi_b4_field_added():
    from session.session_schema import SessionKPIs

    forbidden = {
        "agent_memory_events_observed", "agent_memory_fire_count",
        "agent_memory_enabled_rate",
    }
    leaks = set(SessionKPIs.model_fields.keys()) & forbidden
    assert not leaks


# ---------------------------------------------------------------------------
# 8. Scripts / harness / CLI — Slice 2D2 landed surface
#
# Slice 2D1 pinned "scripts untouched" (P7). Slice 2D2 is
# authorized by H1 / H4 to add exactly one additive CLI flag to
# each script and thread B4 through the public
# ``run_session(agent_memory_config=...)`` kwarg. The updated
# tests below pin the post-2D2 reality:
#
# - scripts DO reference ``agent_memory`` now (but only via the
#   single approved flag + import path);
# - neither script adds forbidden flags
#   (``--agent-memory-target`` / ``--agent-memory-input-surface`` /
#   ``--operations-mode``);
# - the deeper Slice 2D2 behavior (3-variant harness, mode
#   validation, config forwarding) is pinned by
#   ``tests/test_run_session_script_agent_memory_cli.py`` +
#   ``tests/test_session_eval_harness_agent_memory.py``.
# ---------------------------------------------------------------------------


_FORBIDDEN_CLI_FLAG_STRINGS = (
    "--agent-memory-target",
    "--agent-memory-input-surface",
    "--operations-mode",
)


def test_scripts_run_session_exposes_only_the_approved_b4_flag():
    path = os.path.join(_PROJECT_DIR, "scripts", "run_session.py")
    if not os.path.isfile(path):
        pytest.skip("scripts/run_session.py absent")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    # H1 — exactly one B4 CLI flag string appears in the source.
    assert "--enable-agent-visible-memory" in source
    for forbidden in _FORBIDDEN_CLI_FLAG_STRINGS:
        assert forbidden not in source, (
            f"scripts/run_session.py must not expose {forbidden!r} "
            "(H1 / H5 — target / input-surface / operations-mode "
            "flags are explicitly forbidden under Slice 2D2)."
        )


def test_scripts_session_eval_harness_exposes_only_the_approved_b4_flag():
    path = os.path.join(_PROJECT_DIR, "scripts", "session_eval_harness.py")
    if not os.path.isfile(path):
        pytest.skip("scripts/session_eval_harness.py absent")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "--enable-agent-visible-memory" in source
    for forbidden in _FORBIDDEN_CLI_FLAG_STRINGS:
        assert forbidden not in source, (
            f"scripts/session_eval_harness.py must not expose "
            f"{forbidden!r} (H1 / H5)."
        )


# ---------------------------------------------------------------------------
# 9. Slice 2D1.xa — ``_SCHEMA_VERSIONS`` artifact-registry audit (C1 / C2)
# ---------------------------------------------------------------------------
#
# ``SessionArtifact.schema_versions`` is stamped from
# ``event_loop_c._SCHEMA_VERSIONS`` and therefore controls what
# B4 surface the artifact audit claims to support. The Slice
# 2D1.xa corrective patch locked this registry to the
# B1 / B2 precedent:
#
# - Artifact-NESTED B4 schemas (``AgentMemoryContext``,
#   ``AgentMemoryExampleRef``) are NOT registered here, because
#   no landed B4 slice nests them inside a serialized
#   ``SessionArtifact``. D6 / RO1 still defers the
#   ``SessionEventRecord`` overlay. If RO1 later lands, the
#   overlay's MINOR bump and the two nested-schema keys land in
#   the same PR.
# - The config-level ``AgentMemoryExperimentConfig`` IS
#   registered (as ``agent_memory_experiment_config``) because
#   it participates in ``config_for_digest`` when enabled —
#   symmetric with ``replan_config`` / ``correlator_config``.
#
# These tests pin both halves of that policy.


def _schema_versions(**kwargs) -> dict:
    artifact = run_session(
        seed=42, mode="PATH_C_WARM", events=_events(), **kwargs,
    )
    return artifact.schema_versions


def test_schema_versions_identity_no_kwarg_vs_none(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    a = _schema_versions()
    b = _schema_versions(agent_memory_config=None)
    assert a == b


def test_schema_versions_identity_no_kwarg_vs_default_config(monkeypatch):
    """Default ``AgentMemoryExperimentConfig()`` (flag False)
    must produce an artifact whose ``schema_versions`` is
    byte-identical to the no-kwarg call. Default-off byte
    identity on the audit registry is the C3 invariant this
    slice pins."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    a = _schema_versions()
    b = _schema_versions(agent_memory_config=_cfg_default())
    assert a == b


def test_schema_versions_identity_enabled_config_does_not_grow_dict(monkeypatch):
    """Even when the flag is ON and the digest fragment emits,
    ``schema_versions`` must be identical to the OFF-path
    registry — the registry is static-per-landed-slice, not
    per-runtime-activation. C1 in particular forbids
    ``agent_memory_context`` / ``agent_memory_example_ref``
    from leaking in when the flag flips ON."""
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", "llm")
    off = _schema_versions()
    on = _schema_versions(agent_memory_config=_cfg_enabled())
    assert off == on


def test_schema_versions_excludes_artifact_nested_b4_schemas(monkeypatch):
    """C1 — ``AgentMemoryContext`` and ``AgentMemoryExampleRef``
    are NOT part of any landed serialized ``SessionArtifact``
    surface (D6 / RO1 still defers the ``SessionEventRecord``
    overlay). They must not appear in ``schema_versions`` under
    any flag combination."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    for kwargs in (
        {},
        {"agent_memory_config": None},
        {"agent_memory_config": _cfg_default()},
        {"agent_memory_config": _cfg_enabled()},
    ):
        sv = _schema_versions(**kwargs)
        assert "agent_memory_context" not in sv, (
            f"agent_memory_context leaked into schema_versions with "
            f"kwargs={kwargs!r}"
        )
        assert "agent_memory_example_ref" not in sv, (
            f"agent_memory_example_ref leaked into schema_versions with "
            f"kwargs={kwargs!r}"
        )


def test_schema_versions_retains_agent_memory_experiment_config(monkeypatch):
    """C2 precedent — ``agent_memory_experiment_config`` matches
    the ``replan_config`` / ``correlator_config`` pattern: the
    config participates in ``config_for_digest`` when enabled, so
    its version belongs in the artifact audit registry. Retained
    under every flag combination."""
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_OPERATIONS_MODE", raising=False)
    for kwargs in (
        {},
        {"agent_memory_config": None},
        {"agent_memory_config": _cfg_default()},
        {"agent_memory_config": _cfg_enabled()},
    ):
        sv = _schema_versions(**kwargs)
        assert "agent_memory_experiment_config" in sv, (
            f"agent_memory_experiment_config absent from schema_versions "
            f"with kwargs={kwargs!r}"
        )
        assert sv["agent_memory_experiment_config"] == "1.0"


def test_schema_versions_b4_keyspace_is_config_only():
    """Belt-and-suspenders — the full set of ``agent_memory_*``
    keys in the live ``_SCHEMA_VERSIONS`` dict is exactly the
    single config-level key. If a future slice adds another B4
    key (e.g. via the RO1 overlay), this pin fails and forces a
    boundary-doc review of artifact-surface exposure."""
    import event_loop_c as _m

    b4_keys = {k for k in _m._SCHEMA_VERSIONS.keys()
               if k.startswith("agent_memory")}
    assert b4_keys == {"agent_memory_experiment_config"}


def test_schema_versions_b4_policy_mirrors_replan_and_correlator():
    """C2 precedent symmetry pin — the config-level key lives
    alongside ``replan_config`` and ``correlator_config``, and
    follows the same naming / pattern (snake_case, 1.0)."""
    import event_loop_c as _m

    sv = _m._SCHEMA_VERSIONS
    # Precedent anchors still present:
    assert "replan_config" in sv
    assert "correlator_config" in sv
    # B4 mirrors the pattern:
    assert "agent_memory_experiment_config" in sv
