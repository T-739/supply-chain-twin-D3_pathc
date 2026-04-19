"""B4 Slice 2D2: ``scripts/run_session.py`` CLI exposure tests.

Pins the H1–H5 locks landed in this slice for the single-session
CLI. The harness is covered separately in
``tests/test_session_eval_harness_agent_memory.py``.

- H1 — only one new CLI flag (``--enable-agent-visible-memory``).
- H2 — CLI fails fast on ``--enable-agent-visible-memory`` with
  any mode other than ``PATH_C_WARM``.
- H3 — when set, the script builds exactly
  ``AgentMemoryExperimentConfig(enable_agent_visible_memory=True)``
  and passes it through the public
  ``run_session(..., agent_memory_config=...)`` kwarg.
- H5 — no ``--operations-mode`` CLI flag; operations-mode
  dispatch remains env-only.

All tests use ``importlib`` to load the script as a module and
``monkeypatch`` to replace ``run_session`` / ``save_session`` so
the CLI's ``argparse`` / flag-building / forwarding behavior is
exercised without touching the real Path C runtime. This mirrors
the precedent in ``tests/test_cumulative_memory_cli_flag.py``.
"""

from __future__ import annotations

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


def _load_script(path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_artifact(session_id: str = "SID-FAKE"):
    """Build a minimal, schema-valid ``SessionArtifact`` stand-in
    so the CLI's post-``run_session`` ``save_session`` + print
    path exercises without needing a real runtime."""
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


def _install_spy(monkeypatch, mod, captured: dict):
    def _fake_run_session(**kwargs):
        captured.update(kwargs)
        return _fake_artifact()

    monkeypatch.setattr(mod, "run_session", _fake_run_session)
    monkeypatch.setattr(
        mod, "save_session",
        lambda a, d: {"artifact_path": f"{d}/a.json",
                      "memory_path": f"{d}/m.jsonl"},
    )


# ---------------------------------------------------------------------------
# 1. Parser accepts the flag
# ---------------------------------------------------------------------------


def test_parser_accepts_enable_agent_visible_memory(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_accepts_flag",
    )
    captured: dict = {}
    _install_spy(monkeypatch, mod, captured)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_WARM",
        "--enable-agent-visible-memory",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# 2. Mode validation (H2)
# ---------------------------------------------------------------------------


def test_flag_rejects_baseline_static(tmp_path, capsys):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_rejects_baseline_static",
    )
    with pytest.raises(SystemExit) as excinfo:
        mod.main([
            "--seed", "42", "--mode", "BASELINE_STATIC",
            "--enable-agent-visible-memory",
            "--out-dir", str(tmp_path),
        ])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--enable-agent-visible-memory" in err
    assert "PATH_C_WARM" in err


def test_flag_rejects_path_c_cold(tmp_path, capsys):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_rejects_path_c_cold",
    )
    with pytest.raises(SystemExit) as excinfo:
        mod.main([
            "--seed", "42", "--mode", "PATH_C_COLD",
            "--enable-agent-visible-memory",
            "--out-dir", str(tmp_path),
        ])
    assert excinfo.value.code == 2


def test_flag_accepts_path_c_warm(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_accepts_path_c_warm",
    )
    captured: dict = {}
    _install_spy(monkeypatch, mod, captured)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_WARM",
        "--enable-agent-visible-memory",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# 3. Config forwarding (H3)
# ---------------------------------------------------------------------------


def test_flag_off_does_not_pass_agent_memory_config(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_off_no_kwarg",
    )
    captured: dict = {}
    _install_spy(monkeypatch, mod, captured)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_WARM",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    # When the flag is omitted, the CLI must not pass
    # ``agent_memory_config`` at all — it uses ``run_session``'s
    # default-off path byte-identically.
    assert "agent_memory_config" not in captured


def test_flag_on_passes_enabled_config(tmp_path, monkeypatch):
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_on_enabled_config",
    )
    captured: dict = {}
    _install_spy(monkeypatch, mod, captured)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_WARM",
        "--enable-agent-visible-memory",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0

    cfg = captured.get("agent_memory_config")
    from agent_memory.agent_memory_config import AgentMemoryExperimentConfig
    assert isinstance(cfg, AgentMemoryExperimentConfig)
    assert cfg.enable_agent_visible_memory is True
    # H3 — locked shape; CLI never overrides defaults.
    assert cfg.target_agent == "operations"
    assert cfg.context_source == "structured_summary_plus_recent_examples"
    assert cfg.max_recent_examples == 3
    assert cfg.allowed_modes == frozenset({"PATH_C_WARM"})


def test_flag_on_script_does_not_bypass_run_session(tmp_path, monkeypatch):
    """The script must reach B4 through public
    ``run_session(agent_memory_config=...)`` and never by calling
    private helpers directly."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_no_bypass",
    )

    # Spy on the script's run_session binding.
    rs_calls = {"n": 0}

    def _fake_run_session(**kwargs):
        rs_calls["n"] += 1
        return _fake_artifact()

    monkeypatch.setattr(mod, "run_session", _fake_run_session)
    monkeypatch.setattr(
        mod, "save_session",
        lambda a, d: {"artifact_path": "x", "memory_path": "y"},
    )

    # Also spy on the private helper to confirm it is never called
    # directly from the CLI.
    import event_loop_c as _elc
    build_calls = {"n": 0}
    real_build = _elc._build_path_c_main_records

    def _fake_build(**kwargs):
        build_calls["n"] += 1
        return real_build(**kwargs)

    monkeypatch.setattr(_elc, "_build_path_c_main_records", _fake_build)

    rc = mod.main([
        "--seed", "42", "--mode", "PATH_C_WARM",
        "--enable-agent-visible-memory",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert rs_calls["n"] == 1
    # Because we replaced ``run_session`` with a fake, the real
    # ``_build_path_c_main_records`` must NOT have been invoked —
    # proving the CLI's only B4 reach is the public kwarg.
    assert build_calls["n"] == 0


# ---------------------------------------------------------------------------
# 4. No extra CLI surface (H1 / H5)
# ---------------------------------------------------------------------------


def _parser_option_strings(mod) -> set[str]:
    import argparse

    # The script builds its parser inside main(); mimic that to
    # capture the option-string set without running.
    with pytest.MonkeyPatch.context() as mp:
        captured: list[argparse.ArgumentParser] = []
        orig_parse = argparse.ArgumentParser.parse_args

        def _capture_parse(self, argv=None, namespace=None):
            captured.append(self)
            # Short-circuit out of main() by raising; we only
            # wanted the built parser's option set.
            raise _CapturedParser()

        mp.setattr(argparse.ArgumentParser, "parse_args", _capture_parse)

        class _CapturedParser(BaseException):
            pass

        try:
            mod.main(["--seed", "42", "--mode", "PATH_C_WARM", "--out-dir", "/tmp/x"])
        except _CapturedParser:
            pass

    assert captured, "parser was never built"
    parser = captured[-1]
    options: set[str] = set()
    for action in parser._actions:  # pylint: disable=protected-access
        options.update(action.option_strings)
    return options


def test_cli_has_no_agent_memory_target_flag():
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_surface_target",
    )
    options = _parser_option_strings(mod)
    assert "--agent-memory-target" not in options


def test_cli_has_no_agent_memory_input_surface_flag():
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_surface_input_surface",
    )
    options = _parser_option_strings(mod)
    assert "--agent-memory-input-surface" not in options


def test_cli_has_no_operations_mode_flag():
    """H5 — operations_mode dispatch stays env-only. The CLI must
    not expose a ``--operations-mode`` flag."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_surface_operations_mode",
    )
    options = _parser_option_strings(mod)
    assert "--operations-mode" not in options


def test_cli_b4_option_set_is_exactly_one_flag():
    """Belt-and-suspenders pin on H1 — the full set of
    ``agent-memory`` / ``agent_memory`` option strings on the
    parser is exactly the single ``--enable-agent-visible-memory``
    flag."""
    mod = _load_script(
        os.path.join(_SCRIPTS_DIR, "run_session.py"),
        "b4_2d2_cli_surface_single_flag",
    )
    options = _parser_option_strings(mod)
    b4_options = {
        opt for opt in options
        if "agent-memory" in opt or "agent_memory" in opt
        or "agent-visible" in opt or "agent_visible" in opt
    }
    assert b4_options == {"--enable-agent-visible-memory"}
