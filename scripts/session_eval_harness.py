#!/usr/bin/env python3
"""scripts/session_eval_harness.py — Path C Phase 3 eval harness.

Runs BASELINE_STATIC, PATH_C_COLD, PATH_C_WARM over matched inputs
(same seed, same event source, same ``min_records_for_shift``), saves
three session artifacts + three memory JSONL files, produces a
``compare_report.json``, and renders a ``thesis_report.md``.

CLI::

    python scripts/session_eval_harness.py \\
        --seed 42 \\
        --events-source demo_stream \\
        --out-dir runs/phase3/ \\
        [--min-records-for-shift 3] \\
        [--warm-memory synthetic|empty] \\
        [--n-synthetic-records 10]

No wall-clock input. No uuid4. Same command on a fresh clone produces
byte-identical artifacts and reports.

Rollback note (Roadmap §3.F): this script is an additive analysis
tool. If it fails, individual ``scripts/run_session.py`` calls remain
usable as interactive fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from adaptive.adaptive_policy_config import AdaptivePolicyGateConfig  # noqa: E402
from agent_memory.agent_memory_config import AgentMemoryExperimentConfig  # noqa: E402
from correlator.correlator_config import (  # noqa: E402
    KNOWN_CORRELATOR_PATTERN_IDS,
    CorrelatorConfig,
)
from event_loop_c import SUPPORTED_MODES, run_session  # noqa: E402
from learning.cumulative_memory import (  # noqa: E402
    KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES,
    CumulativeMemoryConfig,
    load_cumulative_memory,
)
from learning.episodic_memory import EpisodicMemory  # noqa: E402
from learning.memory_schema import MemoryRecord  # noqa: E402
from replan import ReplanConfig  # noqa: E402
from session.digests import canonical_json  # noqa: E402
from session.session_compare import build_compare_report  # noqa: E402
from session.session_manager import load_session, save_session  # noqa: E402


_DEFAULT_CORRELATOR_WINDOW_SIZE: int = CorrelatorConfig().window_size
_DEFAULT_CUMULATIVE_DEDUPE_POLICY: str = CumulativeMemoryConfig().dedupe_policy


def _build_correlator_config(
    *,
    enable_correlator: bool,
    window_size: int,
    patterns: list[str] | None,
) -> CorrelatorConfig:
    """Same shape as ``scripts/run_session._build_correlator_config``.

    Kept as a local helper (rather than a new shared module) to keep
    the Slice 2D surface minimal.
    """
    if not enable_correlator:
        return CorrelatorConfig()
    kwargs: dict = {
        "enable_correlator": True,
        "window_size": int(window_size),
    }
    if patterns:
        kwargs["enabled_patterns"] = frozenset(patterns)
    return CorrelatorConfig(**kwargs)


def _resolve_prior_session_dir(dir_: str) -> tuple[str, list[MemoryRecord]]:
    """Resolve one user-supplied prior-session directory into a
    (canonical ref, validated rows) pair.

    The canonical ref is the prior session's own ``session_id``
    read from the on-disk ``session_artifact.json``. Filesystem
    paths never enter the cumulative config or any digest
    (per B3 D5 / D10)."""
    if not os.path.isdir(dir_):
        raise FileNotFoundError(
            f"--prior-session-dir {dir_!r} is not an existing directory"
        )
    try:
        artifact = load_session(dir_)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"--prior-session-dir {dir_!r} does not contain a readable "
            f"session_artifact.json"
        ) from None

    canonical_ref = artifact.session_id
    record_dicts = (artifact.memory_snapshot or {}).get("records") or []
    rows = [MemoryRecord.model_validate(r) for r in record_dicts]
    if not rows:
        raise ValueError(
            f"--prior-session-dir {dir_!r} has no memory rows "
            f"(session_artifact.memory_snapshot.records is empty)"
        )
    return canonical_ref, rows


def _build_cumulative_memory_from_dirs(
    *,
    dirs: list[str],
    dedupe_policy: str,
) -> EpisodicMemory:
    """Same shape as ``scripts/run_session._build_cumulative_memory_from_dirs``.

    Kept as a local helper to keep the Slice 2D surface minimal
    (mirrors the correlator-config helper precedent in this file)."""
    refs: list[str] = []
    rows_by_ref: dict[str, list[MemoryRecord]] = {}
    for d in dirs:
        canonical_ref, rows = _resolve_prior_session_dir(d)
        refs.append(canonical_ref)
        rows_by_ref[canonical_ref] = rows

    cfg = CumulativeMemoryConfig(
        prior_session_refs=tuple(refs),
        dedupe_policy=dedupe_policy,
    )

    def resolver(ref: str) -> list[MemoryRecord]:
        return list(rows_by_ref[ref])

    return load_cumulative_memory(cfg, source_resolver=resolver)


_MODE_DIRS = {
    "BASELINE_STATIC": "baseline_static",
    "PATH_C_COLD": "path_c_cold",
    "PATH_C_WARM": "path_c_warm",
}

# Slice 2D2 / H4 — B4 experiment variant tags. When
# ``enable_agent_visible_memory=True`` the harness emits exactly
# these three variants (no PATH_C_COLD). Tag names are locked so
# downstream tests can key on them.
_B4_EXPERIMENT_VARIANT_TAGS: tuple[str, ...] = (
    "baseline_static",
    "path_c_warm_policy_only",
    "path_c_warm_agent_visible_memory",
)


def _build_synthetic_warm_memory(
    *, n: int, session_id_prefix: str = "SYNTHETIC_WARM_SEED",
) -> EpisodicMemory:
    """Deterministic synthetic warm-seed memory for thesis comparison.

    Seeds ``n`` CARRIER_DELAY_ESCALATION records with
    ``sla_preserved=False`` and ``action_taken="EXPEDITE"`` under
    ``AUTO_EXECUTE``. This is the canonical "poor historical SLA"
    scenario from Roadmap §2.E's R1 validation test, reused here so
    the warm session has a warm-phase signal to react to.

    Choosing a seeded memory is part of the experimental *setup*, not
    cheating — the compare report always documents the setup honestly
    and supports_claim is driven by the observed numbers, not by the
    experimenter.
    """
    mem = EpisodicMemory()
    for i in range(int(n)):
        mem.append(MemoryRecord(
            event_id=f"{session_id_prefix}-{i:03d}",
            event_type="CARRIER_DELAY_ESCALATION",
            event_timestamp=f"2026-02-{(i % 28) + 1:02d}T10:00:00+00:00",
            action_taken="EXPEDITE",
            execution_status="executed",
            final_route="AUTO_EXECUTE",
            cost_incurred=250.0,
            sla_preserved=False,
            risk_level="LOW",
            session_id=session_id_prefix,
        ))
    return mem


def run_eval_harness(
    *,
    seed: int,
    events_source: str,
    out_dir: str,
    min_records_for_shift: int = 3,
    warm_memory: str = "synthetic",
    n_synthetic_records: int = 10,
    enable_replan: bool = False,
    enable_correlator: bool = False,
    correlator_window_size: int = _DEFAULT_CORRELATOR_WINDOW_SIZE,
    correlator_patterns: list[str] | None = None,
    prior_session_dirs: list[str] | None = None,
    cumulative_dedupe_policy: str = _DEFAULT_CUMULATIVE_DEDUPE_POLICY,
    enable_agent_visible_memory: bool = False,
) -> dict:
    """Run the Phase 3 harness; return a dict of produced paths.

    ``enable_replan`` defaults to ``False`` to preserve pre-B1
    byte identity of the harness outputs. When set to ``True``, the
    PATH_C_* modes run with ``ReplanConfig(enable_replan=True)``;
    BASELINE_STATIC is unaffected (the orchestrator is never
    consulted in that mode).

    ``enable_correlator`` defaults to ``False`` to preserve pre-B2
    byte identity of the harness outputs. When set to ``True``, all
    three sessions receive the same ``CorrelatorConfig`` (same
    ``window_size``, same ``enabled_patterns``) so the compare
    report's ``correlation_summary`` block reflects a consistent
    parameter set across modes.
    """
    if warm_memory not in ("synthetic", "empty"):
        raise ValueError(
            f"--warm-memory must be 'synthetic' or 'empty', got {warm_memory!r}"
        )
    out_dir = os.fspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    adaptive_config = AdaptivePolicyGateConfig(
        min_records_for_shift=int(min_records_for_shift),
    )
    replan_config = ReplanConfig(enable_replan=bool(enable_replan))
    correlator_config = _build_correlator_config(
        enable_correlator=bool(enable_correlator),
        window_size=int(correlator_window_size),
        patterns=correlator_patterns,
    )

    # B3 cumulative memory (Slice 2D): when at least one prior
    # session dir is supplied, build an EpisodicMemory via the
    # Slice 2B loader and attach it to PATH_C_WARM **only**
    # (D7 workflow rule). Cumulative takes precedence over the
    # synthetic warm seed — providing both is an explicit
    # cumulative run, not a merge. When no dirs are supplied,
    # harness behavior is exactly pre-B3.
    cumulative_prior_memory: EpisodicMemory | None = None
    if prior_session_dirs:
        cumulative_prior_memory = _build_cumulative_memory_from_dirs(
            dirs=list(prior_session_dirs),
            dedupe_policy=cumulative_dedupe_policy,
        )

    warm_seed_memory: EpisodicMemory | None
    if cumulative_prior_memory is not None:
        warm_seed_memory = cumulative_prior_memory
    elif warm_memory == "synthetic":
        warm_seed_memory = _build_synthetic_warm_memory(
            n=int(n_synthetic_records),
        )
    else:
        warm_seed_memory = None

    produced_paths: dict[str, dict[str, str]] = {}
    artifacts = {}

    # B4 Slice 2D2 + 2D3-A — when the experiment flag is ON, the
    # harness emits the locked three-variant set (H4) instead of
    # the default three-mode set. No PATH_C_COLD variant. Only
    # the third variant receives an enabled
    # ``AgentMemoryExperimentConfig``; the first two receive
    # ``agent_memory_config=None`` so their digest identities
    # match a pre-B4 baseline. The branch DOES reach
    # ``session_compare.build_compare_report`` (Slice 2D3-A):
    # compare_report.json + thesis_report.md are emitted over
    # the locked triplet via the additive
    # ``agent_memory_variant_tags`` opt-in kwarg; the conditional
    # ``agent_memory_experiment_summary`` sibling block appears
    # without bumping ``COMPARE_REPORT_SCHEMA_VERSION``.
    if enable_agent_visible_memory:
        # Locked B4 experiment config. Slice 2D2 exposes no CLI
        # knobs for target / context_source / max_recent_examples;
        # D1 / D3 have closed those Literals.
        _b4_enabled_config = AgentMemoryExperimentConfig(
            enable_agent_visible_memory=True,
        )
        _variants: tuple[tuple[str, str, AgentMemoryExperimentConfig | None], ...] = (
            ("baseline_static", "BASELINE_STATIC", None),
            ("path_c_warm_policy_only", "PATH_C_WARM", None),
            (
                "path_c_warm_agent_visible_memory",
                "PATH_C_WARM",
                _b4_enabled_config,
            ),
        )
        for tag, mode, am_cfg in _variants:
            sub_dir = os.path.join(out_dir, tag)
            initial_memory = warm_seed_memory if mode == "PATH_C_WARM" else None
            run_session_kwargs: dict = {
                "seed": int(seed),
                "mode": mode,
                "events_source": events_source,
                "initial_memory": initial_memory,
                "adaptive_config": adaptive_config,
                "replan_config": replan_config,
                "correlator_config": correlator_config,
            }
            # Only thread ``agent_memory_config`` into the ON
            # variant — omitting the kwarg keeps the OFF variants
            # on the pre-B4 byte-identity path.
            if am_cfg is not None:
                run_session_kwargs["agent_memory_config"] = am_cfg
            artifact = run_session(**run_session_kwargs)
            paths = save_session(artifact, sub_dir)
            produced_paths[tag] = paths
            artifacts[tag] = artifact

        # B4 Slice 2D3-A — restore compare_report.json +
        # thesis_report.md emission for the locked three-variant
        # experiment set. The compare call opts in to the new
        # ``agent_memory_experiment_summary`` sibling block by
        # passing ``_B4_EXPERIMENT_VARIANT_TAGS``; the rest of the
        # compare report is the regular three-mode shape (with the
        # experiment's variant tags in place of the default mode
        # names). No private-helper bypass; we still go through the
        # public ``build_compare_report`` API and the existing
        # ``render_thesis_markdown`` renderer.
        compare = build_compare_report(
            artifacts,
            baseline_mode="baseline_static",
            min_records_for_shift=int(min_records_for_shift),
            agent_memory_variant_tags=_B4_EXPERIMENT_VARIANT_TAGS,
        )
        compare_path = os.path.join(out_dir, "compare_report.json")
        with open(compare_path, "w", encoding="utf-8") as f:
            f.write(canonical_json(compare))
            f.flush()
            os.fsync(f.fileno())

        from session.session_compare import render_thesis_markdown

        thesis_path = os.path.join(out_dir, "thesis_report.md")
        with open(thesis_path, "w", encoding="utf-8") as f:
            f.write(render_thesis_markdown(compare))
            f.flush()
            os.fsync(f.fileno())

        return {
            "artifacts": produced_paths,
            "compare_report": compare_path,
            "thesis_report": thesis_path,
            "session_ids": {k: a.session_id for k, a in artifacts.items()},
        }

    for mode in ("BASELINE_STATIC", "PATH_C_COLD", "PATH_C_WARM"):
        sub_dir = os.path.join(out_dir, _MODE_DIRS[mode])
        initial_memory = warm_seed_memory if mode == "PATH_C_WARM" else None
        artifact = run_session(
            seed=int(seed),
            mode=mode,
            events_source=events_source,
            initial_memory=initial_memory,
            adaptive_config=adaptive_config,
            replan_config=replan_config,
            correlator_config=correlator_config,
        )
        paths = save_session(artifact, sub_dir)
        produced_paths[_MODE_DIRS[mode]] = paths
        artifacts[_MODE_DIRS[mode]] = artifact

    # ---- Compare report ----
    compare = build_compare_report(
        artifacts,
        baseline_mode="baseline_static",
        min_records_for_shift=int(min_records_for_shift),
    )
    compare_path = os.path.join(out_dir, "compare_report.json")
    with open(compare_path, "w", encoding="utf-8") as f:
        f.write(canonical_json(compare))
        f.flush()
        os.fsync(f.fileno())

    # ---- Thesis report markdown ----
    from session.session_compare import render_thesis_markdown

    thesis_path = os.path.join(out_dir, "thesis_report.md")
    with open(thesis_path, "w", encoding="utf-8") as f:
        f.write(render_thesis_markdown(compare))
        f.flush()
        os.fsync(f.fileno())

    return {
        "artifacts": produced_paths,
        "compare_report": compare_path,
        "thesis_report": thesis_path,
        "session_ids": {k: a.session_id for k, a in artifacts.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Path C Phase 3 eval harness")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--events-source", default="demo_stream")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--min-records-for-shift", type=int, default=3)
    parser.add_argument("--warm-memory", choices=("synthetic", "empty"), default="synthetic")
    parser.add_argument("--n-synthetic-records", type=int, default=10)
    parser.add_argument(
        "--enable-replan",
        action="store_true",
        help=(
            "Enable B1 bounded-replan for the PATH_C_* modes. Off by "
            "default — pre-B1 byte-identity of harness outputs is "
            "preserved. When set, the compare_report gains a "
            "replan_trace_summary block and the thesis_report gains a "
            "Bounded-replan behavior section."
        ),
    )
    parser.add_argument(
        "--enable-correlator",
        action="store_true",
        help=(
            "Enable B2 event correlator (observability-only sideband) "
            "for all three modes. Off by default — pre-B2 byte identity "
            "of harness outputs is preserved. When set, the compare_"
            "report gains a correlation_summary block and the "
            "thesis_report gains a Correlation observations (B2) "
            "section."
        ),
    )
    parser.add_argument(
        "--correlator-window-size",
        type=int,
        default=_DEFAULT_CORRELATOR_WINDOW_SIZE,
        help=(
            "Sliding-window size used when --enable-correlator is set. "
            f"Default: {_DEFAULT_CORRELATOR_WINDOW_SIZE}. Must be in "
            f"[1, MAX_CORRELATOR_WINDOW]; validated by CorrelatorConfig."
        ),
    )
    parser.add_argument(
        "--correlator-pattern",
        action="append",
        default=None,
        metavar="PATTERN_ID",
        choices=sorted(KNOWN_CORRELATOR_PATTERN_IDS),
        help=(
            "Restrict the correlator to a subset of pattern ids. "
            "Repeatable. Omitted = every known pattern "
            f"({sorted(KNOWN_CORRELATOR_PATTERN_IDS)}). Ignored when "
            "--enable-correlator is not set."
        ),
    )
    parser.add_argument(
        "--prior-session-dir",
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "Load one or more prior session output directories as "
            "B3 cumulative memory. Repeatable. Cumulative memory is "
            "attached to PATH_C_WARM only; BASELINE_STATIC and "
            "PATH_C_COLD are unaffected. When supplied, cumulative "
            "memory REPLACES the synthetic warm seed for PATH_C_WARM. "
            "Each directory must contain a session_artifact.json; "
            "its session_id becomes the canonical prior-session ref "
            "(filesystem paths do not enter the cumulative config or "
            "any digest). Absent by default — pre-B3 byte identity "
            "preserved."
        ),
    )
    parser.add_argument(
        "--cumulative-dedupe-policy",
        default=_DEFAULT_CUMULATIVE_DEDUPE_POLICY,
        choices=sorted(KNOWN_CUMULATIVE_MEMORY_DEDUPE_POLICIES),
        help=(
            "Dedupe policy applied by load_cumulative_memory. "
            f"Default: {_DEFAULT_CUMULATIVE_DEDUPE_POLICY!r}. "
            "Ignored when --prior-session-dir is not set."
        ),
    )
    parser.add_argument(
        "--enable-agent-visible-memory",
        action="store_true",
        help=(
            "Enable the B4 agent-visible memory experiment mode. Off "
            "by default — pre-B4 harness behavior (3-mode set: "
            "baseline_static / path_c_cold / path_c_warm + "
            "compare_report + thesis_report) is preserved. When set, "
            "the harness switches to the locked three-variant B4 "
            "experiment set (baseline_static / "
            "path_c_warm_policy_only / "
            "path_c_warm_agent_visible_memory) and emits "
            "compare_report.json + thesis_report.md over that "
            "triplet. The compare report gains an additive "
            "``agent_memory_experiment_summary`` sibling block; "
            "``COMPARE_REPORT_SCHEMA_VERSION`` stays at \"1.1\". "
            "No target / input-surface / operations-mode CLI flags "
            "are exposed (D1 / D3 / D9)."
        ),
    )
    args = parser.parse_args(argv)

    result = run_eval_harness(
        seed=args.seed,
        events_source=args.events_source,
        out_dir=args.out_dir,
        min_records_for_shift=args.min_records_for_shift,
        warm_memory=args.warm_memory,
        n_synthetic_records=args.n_synthetic_records,
        enable_replan=args.enable_replan,
        enable_correlator=args.enable_correlator,
        correlator_window_size=args.correlator_window_size,
        correlator_patterns=args.correlator_pattern,
        prior_session_dirs=args.prior_session_dir,
        cumulative_dedupe_policy=args.cumulative_dedupe_policy,
        enable_agent_visible_memory=args.enable_agent_visible_memory,
    )

    # Both modes (default 3-mode and B4 experiment triplet) emit
    # compare_report + thesis_report under Slice 2D3-A; the
    # ``in result`` guards stay defensively in case a future
    # caller path returns a result dict without those keys.
    if "compare_report" in result:
        print(f"compare_report={result['compare_report']}")
    if "thesis_report" in result:
        print(f"thesis_report={result['thesis_report']}")
    for mode, sid in result["session_ids"].items():
        print(f"session_id[{mode}]={sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
