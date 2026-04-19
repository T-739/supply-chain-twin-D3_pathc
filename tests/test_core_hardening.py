"""
tests/test_core_hardening.py — D3-Demo Phase 3.5: Core hardening audit locks.

Targeted tests that lock behavior introduced or tightened during the
Phase 3.5 hardening gate. NOT a replacement for existing unit tests —
this file only covers hardening-specific invariants:

  1. Metadata-first parsing: malformed non-empty metadata must fail fast
     (no silent fall-through to text parsing).
  2. Parse source audit trail: outcome.notes carries "[parse=text_fallback]"
     when the dispatcher had to use text parsing.
  3. Demo override audit trail: outcome.notes carries "[DEMO_OVERRIDE on
     HUMAN_REQUIRED]" when auto_approve_escalations forces execution.
  4. Text-fallback rejects non-operational prefixes (APPROVE/VERIFY/
     OVERRIDE/AI/ALT1/ALT2) with an explicit error.
  5. Unknown policy route is surfaced via execution_error, not silently
     swallowed.
"""

import os
import sys
from datetime import datetime, timezone

import pytest

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from execution_adapters import (
    GovernanceActionParseError,
    _parse_operational_type,
    execute_action,
)
from twin_state import TwinState

_TS = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
_BASELINE = os.path.join(_PROJECT_DIR, "data", "configs", "baseline_network.json")


@pytest.fixture
def baseline():
    return TwinState.initialize_from_config(_BASELINE)


# ===========================================================================
# 1. Metadata-first strictness: non-empty-but-unknown metadata must fail
# ===========================================================================


class TestMetadataFirstStrict:
    def test_unknown_nonempty_metadata_raises(self, baseline):
        """Non-empty metadata that isn't in operational set must NOT silently
        fall through to text parsing. This is hardening — before, unknown
        metadata would silently defer to recommended_action parsing."""
        meta = {"recommended_candidate_type": "UNKNOWN_TYPE"}
        gov = {"recommended_action": "EXPEDITE: switch carrier"}
        with pytest.raises(GovernanceActionParseError, match="not a recognized"):
            execute_action(gov, baseline, event_id="H1",
                           governance_meta=meta, timestamp=_TS)

    def test_empty_string_metadata_falls_through(self, baseline):
        """Empty string metadata should fall through to text parsing."""
        meta = {"recommended_candidate_type": ""}
        gov = {"recommended_action": "NO_ACTION"}
        _, outcome = execute_action(gov, baseline, event_id="H2",
                                    governance_meta=meta, timestamp=_TS)
        assert outcome.action_taken == "NO_ACTION"

    def test_missing_metadata_key_falls_through(self, baseline):
        """Metadata dict without recommended_candidate_type should fall through."""
        meta = {"some_other_key": "value"}
        gov = {"recommended_action": "NO_ACTION"}
        _, outcome = execute_action(gov, baseline, event_id="H3",
                                    governance_meta=meta, timestamp=_TS)
        assert outcome.action_taken == "NO_ACTION"

    def test_whitespace_only_metadata_falls_through(self, baseline):
        """Whitespace-only metadata value behaves like empty string."""
        meta = {"recommended_candidate_type": "   "}
        gov = {"recommended_action": "NO_ACTION"}
        _, outcome = execute_action(gov, baseline, event_id="H4",
                                    governance_meta=meta, timestamp=_TS)
        assert outcome.action_taken == "NO_ACTION"


# ===========================================================================
# 2. Parse-source return tuple
# ===========================================================================


class TestParseSourceTuple:
    def test_metadata_path_reports_metadata(self):
        meta = {"recommended_candidate_type": "EXPEDITE"}
        action_type, source = _parse_operational_type({}, meta)
        assert action_type == "EXPEDITE"
        assert source == "metadata"

    def test_text_fallback_reports_text_fallback(self):
        action_type, source = _parse_operational_type(
            {"recommended_action": "TRANSFER: move inventory"}, None,
        )
        assert action_type == "TRANSFER"
        assert source == "text_fallback"


# ===========================================================================
# 3. Audit trail: parse-source annotation on outcome.notes
# ===========================================================================


class TestParseSourceAudit:
    def test_text_fallback_annotates_notes(self, baseline):
        gov = {"recommended_action": "NO_ACTION"}
        _, outcome = execute_action(gov, baseline, event_id="H5", timestamp=_TS)
        assert outcome.notes.startswith("[parse=text_fallback]"), (
            f"Expected text_fallback marker in notes; got: {outcome.notes!r}"
        )

    def test_metadata_path_no_annotation(self, baseline):
        meta = {"recommended_candidate_type": "NO_ACTION"}
        _, outcome = execute_action({}, baseline, event_id="H6",
                                    governance_meta=meta, timestamp=_TS)
        assert "[parse=text_fallback]" not in outcome.notes


# ===========================================================================
# 4. Text-fallback explicit rejection of non-operational layers
# ===========================================================================


class TestTextFallbackLayerRejection:
    @pytest.mark.parametrize("prefix", ["APPROVE", "VERIFY", "OVERRIDE"])
    def test_supervision_prefix_rejected(self, baseline, prefix):
        gov = {"recommended_action": f"{prefix}: do it"}
        with pytest.raises(GovernanceActionParseError, match="non-operational"):
            execute_action(gov, baseline, event_id=f"R1-{prefix}", timestamp=_TS)

    @pytest.mark.parametrize("prefix", ["AI", "ALT1", "ALT2"])
    def test_evaluation_prefix_rejected(self, baseline, prefix):
        gov = {"recommended_action": f"{prefix}: recommend X"}
        with pytest.raises(GovernanceActionParseError, match="non-operational"):
            execute_action(gov, baseline, event_id=f"R2-{prefix}", timestamp=_TS)


# ===========================================================================
# 5. Demo-override audit trail in event_loop
# ===========================================================================


class TestDemoOverrideAudit:
    @pytest.fixture(autouse=True)
    def _ensure_rag(self):
        from rag_setup import build_vector_store, is_store_built
        if not is_store_built():
            build_vector_store()

    def test_demo_override_marker_in_outcome_notes(self):
        """When auto_approve_escalations forces HUMAN_REQUIRED execution,
        the resulting outcome.notes must carry the DEMO_OVERRIDE marker."""
        from event_engine import generate_demo_event_stream
        from event_loop import run_event_loop

        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events, auto_approve_escalations=True)

        for rec in result["event_results"]:
            if rec["execution_status"] == "executed_via_demo_override":
                outcome = rec["execution_outcome"]
                assert outcome is not None
                assert "[DEMO_OVERRIDE" in outcome["notes"], (
                    f"Expected DEMO_OVERRIDE marker; got notes={outcome['notes']!r}"
                )
                return
        pytest.skip("No demo-override execution occurred in this fixture run")

    def test_no_demo_marker_without_override_flag(self):
        """Without auto_approve_escalations, no outcome should carry the
        demo-override marker."""
        from event_engine import generate_demo_event_stream
        from event_loop import run_event_loop

        events = generate_demo_event_stream()[:3]
        result = run_event_loop(events, auto_approve_escalations=False)

        for rec in result["event_results"]:
            outcome = rec["execution_outcome"]
            if outcome is not None:
                assert "[DEMO_OVERRIDE" not in outcome["notes"]


# ===========================================================================
# 6. Unknown route surfaces execution_error (not silent)
# ===========================================================================


class TestUnknownRouteAudit:
    def test_unknown_route_sets_execution_error(self, baseline):
        """If policy_decision.route is malformed/unknown, the event record
        must carry an execution_error string for audit. This is a defense
        against policy_gate contract drift."""
        from event_loop import _route_and_execute
        from event_schema import (
            AffectedEntityRef, EventPayload, EventSeverity, EventType,
        )
        from outcome_store import OutcomeStore

        # Fabricate a minimal event
        event = EventPayload(
            event_id="UR1",
            event_type=EventType.DEMAND_SPIKE,
            severity=EventSeverity.LOW,
            affected_entities=[AffectedEntityRef(
                entity_type="customer_zone", entity_id="CZ_1",
            )],
            timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
            parameters={"delta_units": 1},
        )

        store = OutcomeStore()
        status, outcome, error, new_state = _route_and_execute(
            route="SOMETHING_WEIRD",
            governance_output={"risk_level": "LOW"},
            governance_meta={},
            live_state=baseline,
            event=event,
            outcome_store=store,
            auto_approve_escalations=False,
        )
        assert status == "unknown_route"
        assert outcome is None
        assert error is not None
        assert "SOMETHING_WEIRD" in error
        assert new_state is baseline  # state unchanged


# ===========================================================================
# 7. Mutation discipline: adapter state and apply_action_outcome converge
# ===========================================================================


class TestMutationReplayConsistency:
    def test_expedite_replay_matches_adapter_state(self, baseline):
        """Post-adapter state and post-replay state should agree on the
        mutated fields for EXPEDITE (set-only patches are idempotent)."""
        from execution_adapters import execute_expedite

        adapter_state, outcome = execute_expedite(
            baseline, event_id="M1", timestamp=_TS,
        )
        replay_state = TwinState.initialize_from_config(_BASELINE)
        replay_state.apply_action_outcome(outcome)
        assert replay_state.planned_carrier_id == adapter_state.planned_carrier_id
        assert replay_state.planned_eta_hours == adapter_state.planned_eta_hours

    def test_transfer_replay_matches_adapter_state(self, baseline):
        from execution_adapters import execute_transfer

        adapter_state, outcome = execute_transfer(
            baseline, event_id="M2", timestamp=_TS,
        )
        replay_state = TwinState.initialize_from_config(_BASELINE)
        replay_state.apply_action_outcome(outcome)
        for wid in adapter_state.warehouses:
            assert (replay_state.warehouses[wid].current_inventory
                    == adapter_state.warehouses[wid].current_inventory), (
                f"Mismatch on {wid}"
            )
