'use client';

import type { SessionEventRecordRaw } from '@/lib/types';
import { CollapsibleJson } from './CollapsibleJson';

export interface EventOverlayPanelProps {
  event: SessionEventRecordRaw;
}

function Field({
  label,
  value,
  mono = false,
  testid,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  testid?: string;
}) {
  return (
    <div className="overlay-field">
      <dt className="overlay-field__label">{label}</dt>
      <dd className="overlay-field__value" data-testid={testid}>
        {value === null || value === undefined || value === '' ? (
          <span className="overlay-field__absent">—</span>
        ) : mono ? (
          <code>{String(value)}</code>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

/**
 * Structured Path C overlay inspector.
 *
 * Dual-track contract made visually explicit: GovernanceTruthRef
 * and EffectiveDecisionRef live in two separate side-by-side
 * cards. They NEVER collapse into one value — divergence is the
 * signal. Downstream code must not "merge" them.
 *
 * No field is invented; every cell maps to a canonical path on
 * the serialized SessionEventRecord. Missing fields render as
 * neutral "—" rather than fabricated defaults.
 *
 * The raw JSON of the full overlay is available as a collapsed
 * fallback for anyone who needs the unrendered view.
 */
export function EventOverlayPanel({ event }: EventOverlayPanelProps) {
  const gt = event.governance_truth ?? null;
  const ed = event.effective_decision ?? null;
  const adj = event.adaptive_adjustment ?? null;

  const gtRisk = (gt?.risk_level as string | undefined) ?? null;
  const gtCand =
    (gt?.recommended_candidate_type as string | undefined) ?? null;
  const edRoute = ed?.final_route ?? null;
  const edAction = ed?.action_taken ?? null;
  const edStatus = ed?.execution_status ?? null;
  const edRisk = ed?.effective_risk ?? null;

  // Divergence between governance truth and effective decision
  // is computed structurally (same-string compare on risk_level)
  // so the UI can surface it as a pill — this is NOT compare
  // math, it is the per-event form of the boundary invariant
  // that GovernanceTruthRef != EffectiveDecisionRef is allowed
  // and meaningful.
  const riskDiverged =
    gtRisk !== null &&
    edRisk !== null &&
    gtRisk !== undefined &&
    edRisk !== undefined &&
    gtRisk !== edRisk;

  const adjRuleId =
    (adj?.rule_id as string | undefined) ?? null;
  const adjType =
    (adj?.adjustment_type as string | undefined) ?? null;
  const adjPre =
    (adj?.pre_adjustment_risk as string | undefined) ?? null;
  const adjPost =
    (adj?.post_adjustment_risk as string | undefined) ?? null;

  return (
    <div
      className="overlay-panel"
      data-testid="overlay-panel"
      aria-label="Path C overlay (structured)"
    >
      {/* Header row: mode + policy_route_source */}
      <dl className="overlay-panel__header-grid">
        <Field
          label="mode"
          value={event.mode ?? null}
          mono
          testid="overlay-mode"
        />
        <Field
          label="policy_route_source"
          value={event.policy_route_source ?? null}
          mono
          testid="overlay-policy-route-source"
        />
        <Field
          label="memory_record_id"
          value={event.memory_record_id ?? null}
          mono
          testid="overlay-memory-record-id"
        />
      </dl>

      {/* Dual-track truth — side by side */}
      <div className="overlay-panel__dual-track" data-testid="overlay-dual-track">
        <section
          className="overlay-panel__track overlay-panel__track--governance"
          data-testid="overlay-governance-truth"
          aria-label="Governance truth (Tier 1)"
        >
          <header className="overlay-panel__track-header">
            <span className="overlay-panel__track-tag">Tier 1</span>
            <h5>Governance truth</h5>
          </header>
          <dl className="overlay-panel__track-grid">
            <Field
              label="risk_level"
              value={gtRisk}
              mono
              testid="gt-risk-level"
            />
            <Field
              label="recommended_candidate_type"
              value={gtCand}
              mono
              testid="gt-recommended-candidate-type"
            />
          </dl>
        </section>

        <div
          className={
            'overlay-panel__divider' +
            (riskDiverged ? ' overlay-panel__divider--diverged' : '')
          }
          data-testid="overlay-divider"
          aria-hidden="true"
        >
          {riskDiverged ? 'diverged' : 'aligned'}
        </div>

        <section
          className="overlay-panel__track overlay-panel__track--effective"
          data-testid="overlay-effective-decision"
          aria-label="Effective decision (overlay)"
        >
          <header className="overlay-panel__track-header">
            <span className="overlay-panel__track-tag">Overlay</span>
            <h5>Effective decision</h5>
          </header>
          <dl className="overlay-panel__track-grid">
            <Field
              label="final_route"
              value={edRoute}
              mono
              testid="ed-final-route"
            />
            <Field
              label="action_taken"
              value={edAction}
              mono
              testid="ed-action-taken"
            />
            <Field
              label="execution_status"
              value={edStatus}
              mono
              testid="ed-execution-status"
            />
            <Field
              label="effective_risk"
              value={edRisk}
              mono
              testid="ed-effective-risk"
            />
          </dl>
        </section>
      </div>

      {/* Adaptive adjustment — structured when present, honest when absent */}
      <section
        className="overlay-panel__adjustment"
        data-testid="overlay-adaptive-adjustment"
        aria-label="Adaptive adjustment"
      >
        <h5>Adaptive adjustment</h5>
        {adj === null || adj === undefined ? (
          <p
            className="overlay-panel__absent"
            data-testid="overlay-adjustment-absent"
          >
            None on this event. The effective decision follows the baseline
            policy gate unchanged.
          </p>
        ) : (
          <>
            <dl className="overlay-panel__track-grid">
              <Field label="rule_id" value={adjRuleId} mono testid="adj-rule-id" />
              <Field
                label="adjustment_type"
                value={adjType}
                mono
                testid="adj-adjustment-type"
              />
              <Field
                label="pre_adjustment_risk"
                value={adjPre}
                mono
                testid="adj-pre-adjustment-risk"
              />
              <Field
                label="post_adjustment_risk"
                value={adjPost}
                mono
                testid="adj-post-adjustment-risk"
              />
            </dl>
            <CollapsibleJson
              value={adj}
              label="Full adaptive_adjustment JSON"
              testid="overlay-adjustment-json"
            />
          </>
        )}
      </section>

      <CollapsibleJson
        value={{
          mode: event.mode ?? null,
          policy_route_source: event.policy_route_source ?? null,
          governance_truth: gt,
          effective_decision: ed,
          adaptive_adjustment: adj,
          memory_record_id: event.memory_record_id ?? null,
        }}
        label="Raw overlay JSON"
        testid="overlay-raw-json"
      />
    </div>
  );
}
