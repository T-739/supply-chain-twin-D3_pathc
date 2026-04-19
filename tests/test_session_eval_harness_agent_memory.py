"""B4 Slice 2D2 + Slice 2D3-A: ``scripts/session_eval_harness.py``
exposure tests.

Pins the H1 / H4 / H5 locks landed on the harness, plus the
2D3-A flip on H6 (compare/thesis emission restored under the
``agent_memory_experiment_summary`` opt-in):

- default-OFF harness behavior preserved (``enable_agent_visible_
  memory=False`` still emits the 3-mode set with compare +
  thesis reports);
- ON mode emits exactly three B4 experiment variants
  (``baseline_static`` / ``path_c_warm_policy_only`` /
  ``path_c_warm_agent_visible_memory``), keyed by those tag
  names;
- only the ``path_c_warm_agent_visible_memory`` variant
  receives an enabled ``AgentMemoryExperimentConfig``;
- harness reaches B4 exclusively through
  ``run_session(..., agent_memory_config=...)`` — no private
  helper bypass;
- **Slice 2D3-A flip**: ON mode now emits ``compare_report`` and
  ``thesis_report`` over the locked triplet, opting in to the
  conditional ``agent_memory_experiment_summary`` sibling block
  on the compare report. The block is structural-only;
  ``COMPARE_REPORT_SCHEMA_VERSION`` stays ``"1.1"``;
- no ``--operations-mode`` / ``--agent-memory-target`` /
  ``--agent-memory-input-surface`` CLI flag appears (H5 / H1).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

import pytest


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
_SCRIPTS_DIR = os.path.join(_PROJECT_DIR, "scripts")
for _p in (_SRC_DIR, _PROJECT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_harness(name: str):
    path = os.path.join(_SCRIPTS_DIR, "session_eval_harness.py")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_artifact(session_id: str):
    from session.session_schema import (
        SessionArtifact, SessionConfig, SessionKPIs,
    )
    return SessionArtifact(
        session_id=session_id,
        config=SessionConfig(
            seed=42, mode="PATH_C_WARM",
            events_source="demo_stream",
            initial_memory_digest="",
        ),
        event_records=[],
        memory_snapshot={"records": [], "schema_version": "1.0"},
        kpis=SessionKPIs(),
        schema_versions={},
        notes="",
    )


def _install_run_session_spy(monkeypatch, mod, captured: list[dict]):
    def _fake(**kwargs):
        captured.append({
            "mode": kwargs.get("mode"),
            "agent_memory_config": kwargs.get("agent_memory_config"),
            "has_agent_memory_config_kwarg": "agent_memory_config" in kwargs,
            "initial_memory_is_none": kwargs.get("initial_memory") is None,
        })
        sid = f"SID-{kwargs.get('mode')}-{'AM' if kwargs.get('agent_memory_config') else 'NA'}"
        return _fake_artifact(sid)

    monkeypatch.setattr(mod, "run_session", _fake)


def _install_save_session_stub(monkeypatch, mod):
    monkeypatch.setattr(
        mod, "save_session",
        lambda a, d: {"artifact_path": f"{d}/a.json",
                      "memory_path": f"{d}/m.jsonl"},
    )


# ---------------------------------------------------------------------------
# 1. Default-off harness behavior preserved
# ---------------------------------------------------------------------------


def test_default_off_harness_still_emits_three_mode_set(tmp_path, monkeypatch):
    mod = _load_harness("b4_2d2_harness_default_off")
    captured: list[dict] = []
    _install_run_session_spy(monkeypatch, mod, captured)
    _install_save_session_stub(monkeypatch, mod)

    result = mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
    )

    # 3-mode baseline / cold / warm call pattern unchanged.
    modes = [c["mode"] for c in captured]
    assert modes == ["BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"]
    # None of them receive a B4 config.
    for c in captured:
        assert c["agent_memory_config"] is None
        # Pre-B4 byte identity: the kwarg is simply not passed.
        assert c["has_agent_memory_config_kwarg"] is False

    # The pre-2D2 shape of result dict is preserved.
    assert set(result.keys()) >= {
        "artifacts", "compare_report", "thesis_report", "session_ids"
    }
    assert set(result["artifacts"].keys()) == {
        "baseline_static", "path_c_cold", "path_c_warm",
    }


# ---------------------------------------------------------------------------
# 2. B4 experiment mode emits three variants (H4)
# ---------------------------------------------------------------------------


def test_b4_on_emits_three_locked_variants(tmp_path, monkeypatch):
    mod = _load_harness("b4_2d2_harness_three_variants")
    captured: list[dict] = []
    _install_run_session_spy(monkeypatch, mod, captured)
    _install_save_session_stub(monkeypatch, mod)

    result = mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        enable_agent_visible_memory=True,
    )

    # Exactly three run_session calls in the locked order
    # (H4 — no PATH_C_COLD in the B4 experiment variant set).
    modes = [c["mode"] for c in captured]
    assert modes == ["BASELINE_STATIC", "PATH_C_WARM", "PATH_C_WARM"]

    # Artifact tag set matches the locked three-variant set.
    tag_set = set(result["artifacts"].keys())
    assert tag_set == {
        "baseline_static",
        "path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory",
    }

    # Tag set also mirrored on session_ids mapping.
    assert set(result["session_ids"].keys()) == tag_set


def test_b4_on_variant_tags_exposed_as_module_constant():
    """The locked three-variant tag list is a module constant so
    downstream tooling (and future Slice 2D3 compare-block code)
    can reference it without re-deriving the names."""
    mod = _load_harness("b4_2d2_harness_tag_constant")
    assert hasattr(mod, "_B4_EXPERIMENT_VARIANT_TAGS")
    assert mod._B4_EXPERIMENT_VARIANT_TAGS == (
        "baseline_static",
        "path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory",
    )


# ---------------------------------------------------------------------------
# 3. Only the B4-on warm variant gets the enabled config (H4)
# ---------------------------------------------------------------------------


def test_b4_on_only_third_variant_receives_enabled_config(tmp_path, monkeypatch):
    mod = _load_harness("b4_2d2_harness_third_variant_only")
    captured: list[dict] = []
    _install_run_session_spy(monkeypatch, mod, captured)
    _install_save_session_stub(monkeypatch, mod)

    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        enable_agent_visible_memory=True,
    )

    # Variant 1: baseline_static, no config.
    assert captured[0]["mode"] == "BASELINE_STATIC"
    assert captured[0]["agent_memory_config"] is None
    assert captured[0]["has_agent_memory_config_kwarg"] is False

    # Variant 2: path_c_warm_policy_only, no config.
    assert captured[1]["mode"] == "PATH_C_WARM"
    assert captured[1]["agent_memory_config"] is None
    assert captured[1]["has_agent_memory_config_kwarg"] is False

    # Variant 3: path_c_warm_agent_visible_memory, enabled config.
    from agent_memory.agent_memory_config import AgentMemoryExperimentConfig

    assert captured[2]["mode"] == "PATH_C_WARM"
    cfg = captured[2]["agent_memory_config"]
    assert isinstance(cfg, AgentMemoryExperimentConfig)
    assert cfg.enable_agent_visible_memory is True
    assert captured[2]["has_agent_memory_config_kwarg"] is True


# ---------------------------------------------------------------------------
# 4. Harness does not bypass run_session (H4 / clean public API)
# ---------------------------------------------------------------------------


def test_b4_on_does_not_call_private_build_helper(tmp_path, monkeypatch):
    mod = _load_harness("b4_2d2_harness_no_bypass")
    captured: list[dict] = []
    _install_run_session_spy(monkeypatch, mod, captured)
    _install_save_session_stub(monkeypatch, mod)

    # Spy on the real ``_build_path_c_main_records`` — because we
    # replaced the harness's ``run_session`` with a fake, the real
    # private helper must never be hit.
    import event_loop_c as _elc
    build_calls = {"n": 0}
    real_build = _elc._build_path_c_main_records

    def _fake_build(**kwargs):
        build_calls["n"] += 1
        return real_build(**kwargs)

    monkeypatch.setattr(_elc, "_build_path_c_main_records", _fake_build)

    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        enable_agent_visible_memory=True,
    )

    assert len(captured) == 3, (
        "harness should reach run_session 3 times under B4 mode"
    )
    assert build_calls["n"] == 0, (
        "harness must NOT call _build_path_c_main_records "
        "directly — it must go through run_session(...)"
    )


# ---------------------------------------------------------------------------
# 5. Compare-report block coupling — Slice 2D3-A flip
# ---------------------------------------------------------------------------


def test_b4_on_result_emits_compare_and_thesis_reports(tmp_path, monkeypatch):
    """Slice 2D3-A flip of the prior 2D2 H6 deferral: the B4 ON
    mode now emits ``compare_report.json`` + ``thesis_report.md``
    over the locked three-variant triplet."""
    mod = _load_harness("b4_2d3a_harness_emits_compare")
    captured: list[dict] = []
    _install_run_session_spy(monkeypatch, mod, captured)
    _install_save_session_stub(monkeypatch, mod)

    result = mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        enable_agent_visible_memory=True,
    )

    assert "compare_report" in result
    assert "thesis_report" in result
    # Files actually exist.
    assert os.path.isfile(result["compare_report"])
    assert os.path.isfile(result["thesis_report"])


def test_b4_on_compare_report_carries_agent_memory_block(tmp_path, monkeypatch):
    """The emitted compare report must carry the conditional
    ``agent_memory_experiment_summary`` sibling block keyed off the
    locked triplet tags."""
    import json as _json

    mod = _load_harness("b4_2d3a_harness_block_present")
    captured: list[dict] = []
    _install_run_session_spy(monkeypatch, mod, captured)
    _install_save_session_stub(monkeypatch, mod)

    result = mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        enable_agent_visible_memory=True,
    )

    with open(result["compare_report"], "r", encoding="utf-8") as f:
        report = _json.load(f)

    assert "agent_memory_experiment_summary" in report
    block = report["agent_memory_experiment_summary"]
    assert block["variant_tags"] == [
        "baseline_static",
        "path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory",
    ]
    # Block opt-in must NOT bump the report schema version.
    assert report["schema_version"] == "1.1"


def test_b4_on_compare_report_uses_public_build_compare_report_kwarg(
    tmp_path, monkeypatch,
):
    """The harness must reach the B4 compare block exclusively via
    the public ``agent_memory_variant_tags`` kwarg on
    ``build_compare_report`` — no private helper bypass."""
    mod = _load_harness("b4_2d3a_harness_kwarg_path")
    _install_run_session_spy(monkeypatch, mod, [])
    _install_save_session_stub(monkeypatch, mod)

    captured_kwargs: list[dict] = []
    real_build = mod.build_compare_report

    def _spy_build(*args, **kwargs):
        captured_kwargs.append(dict(kwargs))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(mod, "build_compare_report", _spy_build)

    mod.run_eval_harness(
        seed=42,
        events_source="demo_stream",
        out_dir=str(tmp_path),
        enable_agent_visible_memory=True,
    )

    assert len(captured_kwargs) == 1
    kw = captured_kwargs[0]
    assert kw.get("agent_memory_variant_tags") == (
        "baseline_static",
        "path_c_warm_policy_only",
        "path_c_warm_agent_visible_memory",
    )
    assert kw.get("baseline_mode") == "baseline_static"


# ---------------------------------------------------------------------------
# 6. No operations_mode publicization (H5)
# ---------------------------------------------------------------------------


def test_run_eval_harness_signature_has_no_operations_mode():
    """``run_eval_harness``'s public signature must not expose an
    ``operations_mode`` parameter. Operations-mode dispatch stays
    env-only under D9 / H5."""
    import inspect
    mod = _load_harness("b4_2d2_harness_sig")
    sig = inspect.signature(mod.run_eval_harness)
    assert "operations_mode" not in sig.parameters


def test_run_eval_harness_signature_gained_exactly_the_b4_flag():
    """``run_eval_harness`` gained exactly one B4-related kwarg —
    the ``enable_agent_visible_memory`` flag. Any other
    ``agent_memory`` / ``agent_visible`` parameter name would
    trip this pin and force a boundary review."""
    import inspect
    mod = _load_harness("b4_2d2_harness_sig_single_flag")
    sig = inspect.signature(mod.run_eval_harness)
    b4_params = [
        p for p in sig.parameters
        if "agent_memory" in p or "agent_visible" in p
    ]
    assert b4_params == ["enable_agent_visible_memory"]
    assert sig.parameters["enable_agent_visible_memory"].default is False


def _harness_parser_options() -> set[str]:
    mod = _load_harness("b4_2d2_harness_parser_options")
    captured: list[argparse.ArgumentParser] = []
    orig = argparse.ArgumentParser.parse_args

    class _Stop(BaseException):
        pass

    def _capture(self, argv=None, namespace=None):
        captured.append(self)
        raise _Stop()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(argparse.ArgumentParser, "parse_args", _capture)
        try:
            mod.main(["--seed", "42", "--out-dir", "/tmp/x"])
        except _Stop:
            pass
    assert captured
    parser = captured[-1]
    options: set[str] = set()
    for action in parser._actions:  # pylint: disable=protected-access
        options.update(action.option_strings)
    return options


def test_harness_cli_has_no_operations_mode_flag():
    options = _harness_parser_options()
    assert "--operations-mode" not in options


def test_harness_cli_has_exactly_one_b4_flag():
    options = _harness_parser_options()
    b4_options = {
        opt for opt in options
        if "agent-memory" in opt or "agent_memory" in opt
        or "agent-visible" in opt or "agent_visible" in opt
    }
    assert b4_options == {"--enable-agent-visible-memory"}


def test_harness_cli_has_no_agent_memory_target_or_input_surface_flag():
    options = _harness_parser_options()
    assert "--agent-memory-target" not in options
    assert "--agent-memory-input-surface" not in options
