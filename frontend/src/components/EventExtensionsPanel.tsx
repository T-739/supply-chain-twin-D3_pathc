'use client';

import type { SessionEventRecordRaw } from '@/lib/types';
import { CollapsibleJson } from './CollapsibleJson';

export interface EventExtensionsPanelProps {
  event: SessionEventRecordRaw;
}

function pickString(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null;
}

function pickNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function pickArray<T = unknown>(v: unknown): T[] | null {
  return Array.isArray(v) ? (v as T[]) : null;
}

// ----------------------------- B1 ------------------------------

function ReplanTraceBlock({ event }: { event: SessionEventRecordRaw }) {
  const trace = pickArray<Record<string, unknown>>(event.replan_trace);
  const hasTrace = trace !== null && trace.length > 0;

  return (
    <div className="ext-block" data-testid="ext-b1-trace-block">
      <header className="ext-block__header">
        <strong>B1 · Replan trace</strong>
        <span
          className={
            'ext-block__presence' +
            (hasTrace
              ? ' ext-block__presence--present'
              : ' ext-block__presence--absent')
          }
          data-testid="ext-b1-presence"
        >
          {hasTrace ? 'present' : 'absent'}
        </span>
      </header>
      {hasTrace && (
        <>
          <table className="ext-block__table" data-testid="ext-b1-trace-table">
            <thead>
              <tr>
                <th>attempt</th>
                <th>final_route</th>
                <th>action_taken</th>
                <th>execution_status</th>
                <th>trigger_type</th>
              </tr>
            </thead>
            <tbody>
              {trace!.map((attempt, i) => {
                const triggerObj =
                  (attempt?.trigger as Record<string, unknown> | undefined) ??
                  null;
                return (
                  <tr key={i} data-testid={`ext-b1-trace-row-${i}`}>
                    <td>{pickNumber(attempt?.attempt_index) ?? i}</td>
                    <td>
                      <code>{pickString(attempt?.attempt_final_route) ?? '—'}</code>
                    </td>
                    <td>
                      <code>{pickString(attempt?.attempt_action_taken) ?? '—'}</code>
                    </td>
                    <td>
                      <code>
                        {pickString(attempt?.attempt_execution_status) ?? '—'}
                      </code>
                    </td>
                    <td>
                      <code>
                        {pickString(triggerObj?.trigger_type) ?? '—'}
                      </code>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <CollapsibleJson
            value={trace}
            label="Raw replan_trace JSON"
            testid="ext-b1-trace-json"
          />
        </>
      )}
    </div>
  );
}

function ReplanTriggersBlock({ event }: { event: SessionEventRecordRaw }) {
  const triggers = pickArray<Record<string, unknown>>(event.replan_triggers);
  const hasTriggers = triggers !== null && triggers.length > 0;

  return (
    <div className="ext-block" data-testid="ext-b1-triggers-block">
      <header className="ext-block__header">
        <strong>B1 · Replan triggers</strong>
        <span
          className={
            'ext-block__presence' +
            (hasTriggers
              ? ' ext-block__presence--present'
              : ' ext-block__presence--absent')
          }
          data-testid="ext-b1-triggers-presence"
        >
          {hasTriggers ? 'present' : 'absent'}
        </span>
      </header>
      {hasTriggers && (
        <>
          <table
            className="ext-block__table"
            data-testid="ext-b1-triggers-table"
          >
            <thead>
              <tr>
                <th>attempt</th>
                <th>trigger_type</th>
                <th>rule_id</th>
              </tr>
            </thead>
            <tbody>
              {triggers!.map((t, i) => (
                <tr key={i} data-testid={`ext-b1-triggers-row-${i}`}>
                  <td>{pickNumber(t?.attempt_index) ?? i}</td>
                  <td>
                    <code>{pickString(t?.trigger_type) ?? '—'}</code>
                  </td>
                  <td>
                    <code>{pickString(t?.trigger_rule_id) ?? '—'}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <CollapsibleJson
            value={triggers}
            label="Raw replan_triggers JSON"
            testid="ext-b1-triggers-json"
          />
        </>
      )}
    </div>
  );
}

// ----------------------------- B2 ------------------------------

function CorrelationBlock({ event }: { event: SessionEventRecordRaw }) {
  const ctx = event.correlation_context ?? null;
  const hasCtx = ctx !== null && ctx !== undefined;

  const signals = pickArray<Record<string, unknown>>(ctx?.signals);
  const windowSize = pickNumber(ctx?.window_size);
  const considered = pickNumber(ctx?.window_events_considered);

  return (
    <div className="ext-block" data-testid="ext-b2-block">
      <header className="ext-block__header">
        <strong>B2 · Correlation context</strong>
        <span
          className={
            'ext-block__presence' +
            (hasCtx
              ? ' ext-block__presence--present'
              : ' ext-block__presence--absent')
          }
          data-testid="ext-b2-presence"
        >
          {hasCtx ? 'present' : 'absent'}
        </span>
      </header>
      {hasCtx && (
        <>
          <dl className="ext-block__meta">
            <div>
              <dt>window_size</dt>
              <dd data-testid="ext-b2-window-size">
                {windowSize === null ? '—' : windowSize}
              </dd>
            </div>
            <div>
              <dt>window_events_considered</dt>
              <dd data-testid="ext-b2-window-events">
                {considered === null ? '—' : considered}
              </dd>
            </div>
            <div>
              <dt>signals</dt>
              <dd data-testid="ext-b2-signals-count">
                {signals === null ? '—' : signals.length}
              </dd>
            </div>
          </dl>
          {signals !== null && signals.length > 0 && (
            <table
              className="ext-block__table"
              data-testid="ext-b2-signals-table"
            >
              <thead>
                <tr>
                  <th>pattern_id</th>
                  <th>triggering_event_id</th>
                  <th>matched_conditions</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, i) => {
                  const conds = pickArray<string>(sig?.matched_conditions);
                  return (
                    <tr key={i} data-testid={`ext-b2-signals-row-${i}`}>
                      <td>
                        <code>{pickString(sig?.pattern_id) ?? '—'}</code>
                      </td>
                      <td>
                        <code>
                          {pickString(sig?.triggering_event_id) ?? '—'}
                        </code>
                      </td>
                      <td>
                        {conds === null || conds.length === 0 ? (
                          '—'
                        ) : (
                          <ul className="ext-block__chips">
                            {conds.map((c) => (
                              <li key={c}>
                                <code>{c}</code>
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {signals !== null && signals.length === 0 && (
            <p
              className="ext-block__note"
              data-testid="ext-b2-empty-signals"
            >
              Correlator ran and found no matching signals for this event.
              Presence of an empty context is itself information — it
              distinguishes "ran, matched nothing" from "did not run".
            </p>
          )}
          <CollapsibleJson
            value={ctx}
            label="Raw correlation_context JSON"
            testid="ext-b2-json"
          />
        </>
      )}
    </div>
  );
}

// ----------------------------- B3 ------------------------------

function B3Block() {
  return (
    <div className="ext-block" data-testid="ext-b3-block">
      <header className="ext-block__header">
        <strong>B3 · Cumulative memory</strong>
        <span
          className="ext-block__presence ext-block__presence--na"
          data-testid="ext-b3-presence"
        >
          not surfaced at event level
        </span>
      </header>
      <p className="ext-block__note">
        Cumulative memory is modelled as <strong>session-level</strong>{' '}
        provenance — it lives on <code>memory_snapshot</code> and (when
        present) the compare report&apos;s{' '}
        <code>cumulative_memory_summary</code> sibling block. There is no
        per-event B3 overlay, and this page will not fabricate one. See
        the session summary above for session-level memory provenance.
      </p>
    </div>
  );
}

// ----------------------------- B4 ------------------------------

function B4Block() {
  return (
    <div className="ext-block" data-testid="ext-b4-block">
      <header className="ext-block__header">
        <strong>B4 · Agent-visible memory (experiment)</strong>
        <span
          className="ext-block__presence ext-block__presence--na"
          data-testid="ext-b4-presence"
        >
          not surfaced at event level
        </span>
      </header>
      <ul className="ext-block__labels" data-testid="ext-b4-labels">
        <li>experiment</li>
        <li>default-off</li>
        <li>compare-only</li>
      </ul>
      <p className="ext-block__note">
        B4 is an independent experiment branch. It does not emit a
        per-event overlay on <code>SessionEventRecord</code>; its footprint
        lives inside the compare report (opt-in{' '}
        <code>agent_memory_experiment_summary</code> sibling block) and
        only activates when an explicit CLI / kwarg flag is set. The
        Runtime page treats B4 as a labeled boundary and does not render
        it as a normal per-event detail layer.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------

export function EventExtensionsPanel({ event }: EventExtensionsPanelProps) {
  return (
    <div
      className="ext-panel"
      data-testid="ext-panel"
      aria-label="Extensions (structured)"
    >
      <ReplanTraceBlock event={event} />
      <ReplanTriggersBlock event={event} />
      <CorrelationBlock event={event} />
      <B3Block />
      <B4Block />
    </div>
  );
}
