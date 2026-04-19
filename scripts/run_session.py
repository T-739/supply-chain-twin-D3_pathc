#!/usr/bin/env python3
"""scripts/run_session.py — Path C Phase 1 minimal CLI.

Usage example::

    python scripts/run_session.py --seed 42 --mode BASELINE_STATIC \\
        --events-source demo_stream --out-dir /tmp/pathc_session

Writes:
  {out_dir}/session_artifact.json
  {out_dir}/memory.jsonl

Not a product CLI. No UI, no progress bar, no pretty printing.
Deterministic by construction — same args produce byte-identical output.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

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
from session.session_manager import load_session, save_session  # noqa: E402


_DEFAULT_CORRELATOR_WINDOW_SIZE: int = CorrelatorConfig().window_size
_DEFAULT_CUMULATIVE_DEDUPE_POLICY: str = CumulativeMemoryConfig().dedupe_policy


def _resolve_prior_session_dir(dir_: str) -> tuple[str, list[MemoryRecord]]:
    """Resolve one user-supplied prior-session directory into a
    (canonical ref, validated rows) pair.

    The canonical ref is the prior session's own ``session_id``,
    read from the on-disk ``session_artifact.json``. **Raw
    filesystem paths never become the ref** (per D5 / D10).

    Raises
    ------
    FileNotFoundError
        When the directory or its ``session_artifact.json`` is
        missing.
    ValueError
        When the prior session has no memory rows.
    """
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
    """Convert an ordered list of prior-session directories into
    an ``EpisodicMemory`` via the Slice 2B loader.

    The CLI layer owns all filesystem access: it resolves each
    dir into a canonical ref + a list of validated
    ``MemoryRecord`` instances, then builds a
    ``CumulativeMemoryConfig`` (refs only — no paths) and a
    resolver closure. The loader itself sees nothing but refs
    and a callable (D10).

    Duplicate dirs are allowed — if two dirs resolve to the same
    ref, the loader's dedupe policy silently drops equal rows
    and raises ``CumulativeMemoryCollisionError`` on mismatched
    rows.
    """
    refs: list[str] = []
    rows_by_ref: dict[str, list[MemoryRecord]] = {}
    for d in dirs:
        canonical_ref, rows = _resolve_prior_session_dir(d)
        refs.append(canonical_ref)
        # If the same ref was already resolved from an earlier
        # dir, prefer the latest rows — the loader's dedupe rule
        # will catch any row-content disagreement.
        rows_by_ref[canonical_ref] = rows

    cfg = CumulativeMemoryConfig(
        prior_session_refs=tuple(refs),
        dedupe_policy=dedupe_policy,
    )

    def resolver(ref: str) -> list[MemoryRecord]:
        return list(rows_by_ref[ref])

    return load_cumulative_memory(cfg, source_resolver=resolver)


def _build_correlator_config(
    *,
    enable_correlator: bool,
    window_size: int,
    patterns: list[str] | None,
) -> CorrelatorConfig:
    """Build a ``CorrelatorConfig`` from parsed CLI arguments.

    Disabled (default) uses the plain ``CorrelatorConfig()`` so
    byte-identity with pre-B2 runs is preserved. Enabled threads the
    window size through and — if ``patterns`` is provided — restricts
    ``enabled_patterns`` to that subset (validated by
    ``CorrelatorConfig.__post_init__``).
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Path C Phase 1 session runner")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--mode",
        choices=list(SUPPORTED_MODES),
        default="BASELINE_STATIC",
    )
    parser.add_argument("--events-source", default="demo_stream")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--enable-replan",
        action="store_true",
        help=(
            "Enable B1 bounded-replan. Off by default — pre-B1 "
            "behavior. When set, PATH_C_* modes run with "
            "ReplanConfig(enable_replan=True); BASELINE_STATIC is "
            "unaffected."
        ),
    )
    parser.add_argument(
        "--enable-correlator",
        action="store_true",
        help=(
            "Enable B2 event correlator (observability-only sideband). "
            "Off by default — pre-B2 behavior. When set, each event's "
            "SessionEventRecord gains a populated correlation_context; "
            "routing / adaptive / replan decisions are unchanged."
        ),
    )
    parser.add_argument(
        "--correlator-window-size",
        type=int,
        default=_DEFAULT_CORRELATOR_WINDOW_SIZE,
        help=(
            "Sliding-window size (event-stream ordinals) used when "
            f"--enable-correlator is set. Default: "
            f"{_DEFAULT_CORRELATOR_WINDOW_SIZE}. Must be in "
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
            "Repeatable. Omitted = use every known pattern "
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
            "Load a prior session's memory rows into this run's "
            "initial_memory (B3 cumulative memory). Repeatable. "
            "Only valid when --mode PATH_C_WARM. Each directory must "
            "contain a session_artifact.json; its session_id becomes "
            "the canonical prior-session ref (filesystem paths do not "
            "enter the cumulative config or any digest). Absent by "
            "default — pre-B3 behavior preserved."
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
            "Enable the B4 agent-visible memory experiment branch. "
            "Off by default — pre-B4 byte identity preserved. Only "
            "valid with --mode PATH_C_WARM (D5 allowed_modes). "
            "Operations-mode dispatch stays env-only (D9); "
            "SUPPLY_CHAIN_TWIN_OPERATIONS_MODE=llm is still required "
            "for B4 to actually inject at runtime. No target / "
            "input-surface CLI flags are exposed (D1 / D3 closed the "
            "corresponding Literals)."
        ),
    )
    args = parser.parse_args(argv)

    replan_config = ReplanConfig(enable_replan=bool(args.enable_replan))
    correlator_config = _build_correlator_config(
        enable_correlator=bool(args.enable_correlator),
        window_size=int(args.correlator_window_size),
        patterns=args.correlator_pattern,
    )

    # B3 cumulative memory is a caller-side workflow: the CLI
    # enforces PATH_C_WARM-only attachment and never mutates the
    # core run_session API. Absent flag => initial_memory=None =>
    # pre-B3 byte identity preserved.
    prior_dirs = args.prior_session_dir or []
    initial_memory = None
    if prior_dirs:
        if args.mode != "PATH_C_WARM":
            parser.error(
                "--prior-session-dir may only be used with "
                "--mode PATH_C_WARM (B3 workflow rule D7). Got "
                f"mode={args.mode!r}."
            )
        initial_memory = _build_cumulative_memory_from_dirs(
            dirs=prior_dirs,
            dedupe_policy=args.cumulative_dedupe_policy,
        )

    # B4 agent-visible memory is a caller-side workflow: the CLI
    # enforces PATH_C_WARM-only at the script layer (Slice 2D2 /
    # H2). Absent flag => agent_memory_config=None => pre-B4
    # byte identity preserved. When set, the CLI builds the
    # single locked config shape (H3 — no target / input-surface
    # options exposed because D1 / D3 already close the Literals).
    agent_memory_config = None
    if args.enable_agent_visible_memory:
        if args.mode != "PATH_C_WARM":
            parser.error(
                "--enable-agent-visible-memory may only be used "
                "with --mode PATH_C_WARM (B4 D5 / H2 workflow rule). "
                f"Got mode={args.mode!r}."
            )
        agent_memory_config = AgentMemoryExperimentConfig(
            enable_agent_visible_memory=True,
        )

    run_session_kwargs: dict = {
        "seed": args.seed,
        "mode": args.mode,
        "events_source": args.events_source,
        "initial_memory": initial_memory,
        "replan_config": replan_config,
        "correlator_config": correlator_config,
    }
    # Only pass ``agent_memory_config`` when the user asked for it;
    # omitting the kwarg keeps ``run_session`` on its pre-B4
    # default-off path byte-identically.
    if agent_memory_config is not None:
        run_session_kwargs["agent_memory_config"] = agent_memory_config

    artifact = run_session(**run_session_kwargs)
    paths = save_session(artifact, args.out_dir)

    print(f"session_id={artifact.session_id}")
    print(f"artifact={paths['artifact_path']}")
    print(f"memory={paths['memory_path']}")
    print(f"events_observed={artifact.kpis.events_observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
