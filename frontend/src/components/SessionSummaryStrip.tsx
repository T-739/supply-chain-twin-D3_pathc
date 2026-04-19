'use client';

import type {
  SessionArtifactRaw,
  SessionArtifactResponse,
  SessionEventRecordRaw,
  SessionSummary,
} from '@/lib/types';

export interface SessionSummaryStripProps {
  summary: SessionSummary | null;
  artifactResponse: SessionArtifactResponse | null;
}

function fmtOpt(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined) return '—';
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  return v.toFixed(digits);
}

/**
 * Count a structural distribution of a single string-valued
 * overlay field across the serialized event records. This is
 * a count, not a KPI — no rate, no percentage, no success
 * interpretation. It simply tallies the values the artifact
 * already contains, which is what any honest read-only
 * surface would do when asked "what did the overlay emit?".
 */
function countBy(
  events: SessionEventRecordRaw[],
  picker: (rec: SessionEventRecordRaw) => string | null | undefined,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const rec of events) {
    const v = picker(rec);
    if (typeof v !== 'string' || v.length === 0) continue;
    out[v] = (out[v] ?? 0) + 1;
  }
  return out;
}

function Distribution({
  dist,
  testid,
}: {
  dist: Record<string, number>;
  testid?: string;
}) {
  const keys = Object.keys(dist).sort();
  if (keys.length === 0) {
    return (
      <span className="summary-distribution__empty" data-testid={testid}>
        —
      </span>
    );
  }
  return (
    <ul className="summary-distribution" data-testid={testid}>
      {keys.map((k) => (
        <li key={k}>
          <code>{k}</code>
          <span className="summary-distribution__count">{dist[k]}</span>
        </li>
      ))}
    </ul>
  );
}

function memoryRowCount(raw: SessionArtifactRaw | null | undefined): number | null {
  const snap = raw?.memory_snapshot;
  if (!snap || typeof snap !== 'object') return null;
  const recs = (snap as Record<string, unknown>).records;
  return Array.isArray(recs) ? recs.length : null;
}

/**
 * Compact per-session summary strip.
 *
 * Phase 3B deepens the strip using only already-serialized
 * artifact data:
 *   - session facts block (session_id, mode, seed, events_source)
 *   - shallow KPIs from the backend summary
 *   - memory snapshot presence + row count (when available)
 *   - schema_versions stamp
 *   - structural route mix / action mix tallied from
 *     event_records[].effective_decision.*
 *
 * No compare math, no new KPIs, no narrative.
 */
export function SessionSummaryStrip({
  summary,
  artifactResponse,
}: SessionSummaryStripProps) {
  if (!summary && !artifactResponse) {
    return null;
  }
  const sid = summary?.session_id ?? null;
  const mode = summary?.mode ?? null;
  const memoryPresent =
    summary?.memory_jsonl_present ??
    artifactResponse?.memory_jsonl_present ??
    false;
  const loadable =
    summary?.session_artifact_loadable ??
    artifactResponse?.session_artifact_loadable ??
    false;

  const raw = artifactResponse?.session_artifact_raw ?? null;
  const cfg = raw?.config ?? null;
  const seed = typeof cfg?.seed === 'number' ? cfg.seed : null;
  const eventsSource =
    typeof cfg?.events_source === 'string' ? cfg.events_source : null;
  const events: SessionEventRecordRaw[] = Array.isArray(raw?.event_records)
    ? (raw!.event_records as SessionEventRecordRaw[])
    : [];
  const routeMix = countBy(events, (r) =>
    (r.effective_decision?.final_route as string | undefined) ?? null,
  );
  const actionMix = countBy(events, (r) => {
    const v = r.effective_decision?.action_taken;
    return typeof v === 'string' ? v : null;
  });
  const memRows = memoryRowCount(raw);
  const schemaVersions = raw?.schema_versions ?? null;

  return (
    <section
      className="session-summary-strip"
      data-testid="session-summary-strip"
      aria-label="Session summary"
    >
      <dl className="session-summary-strip__grid">
        <div>
          <dt>Variant tag</dt>
          <dd>
            <code data-testid="summary-variant-tag">
              {summary?.variant_tag ?? artifactResponse?.variant_tag ?? '—'}
            </code>
          </dd>
        </div>
        <div>
          <dt>session_id</dt>
          <dd>{sid ? <code>{sid}</code> : '—'}</dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd data-testid="summary-mode">{mode ?? '—'}</dd>
        </div>
        <div>
          <dt>seed</dt>
          <dd data-testid="summary-seed">{seed === null ? '—' : seed}</dd>
        </div>
        <div>
          <dt>events_source</dt>
          <dd data-testid="summary-events-source">
            {eventsSource ? <code>{eventsSource}</code> : '—'}
          </dd>
        </div>
        <div>
          <dt>events_observed</dt>
          <dd>{summary?.events_observed ?? '—'}</dd>
        </div>
        <div>
          <dt>events_with_outcome</dt>
          <dd>{summary?.events_with_outcome ?? '—'}</dd>
        </div>
        <div>
          <dt>sla_preservation_rate</dt>
          <dd>{fmtOpt(summary?.sla_preservation_rate ?? null)}</dd>
        </div>
        <div>
          <dt>auto_execute_success_rate</dt>
          <dd>{fmtOpt(summary?.auto_execute_success_rate ?? null)}</dd>
        </div>
        <div>
          <dt>avg_cost</dt>
          <dd>{fmtOpt(summary?.avg_cost ?? null)}</dd>
        </div>
        <div>
          <dt>memory.jsonl</dt>
          <dd>{memoryPresent ? 'present' : 'absent'}</dd>
        </div>
        <div>
          <dt>memory_snapshot rows</dt>
          <dd data-testid="summary-memory-rows">
            {memRows === null ? '—' : memRows}
          </dd>
        </div>
        <div>
          <dt>artifact loadable</dt>
          <dd>{loadable ? 'yes' : 'no'}</dd>
        </div>
      </dl>

      <div
        className="session-summary-strip__mixes"
        data-testid="summary-mixes"
      >
        <div>
          <dt>route mix (effective_decision.final_route)</dt>
          <dd>
            <Distribution dist={routeMix} testid="summary-route-mix" />
          </dd>
        </div>
        <div>
          <dt>action mix (effective_decision.action_taken)</dt>
          <dd>
            <Distribution dist={actionMix} testid="summary-action-mix" />
          </dd>
        </div>
      </div>

      {schemaVersions && Object.keys(schemaVersions).length > 0 && (
        <div
          className="session-summary-strip__schema-versions"
          data-testid="summary-schema-versions"
        >
          <dt>schema_versions</dt>
          <dd>
            <ul className="summary-distribution">
              {Object.keys(schemaVersions)
                .sort()
                .map((key) => (
                  <li key={key}>
                    <code>{key}</code>
                    <span className="summary-distribution__count">
                      v{schemaVersions[key]}
                    </span>
                  </li>
                ))}
            </ul>
          </dd>
        </div>
      )}

      {artifactResponse && artifactResponse.load_warnings.length > 0 && (
        <ul
          className="session-summary-strip__warnings"
          data-testid="summary-load-warnings"
        >
          {artifactResponse.load_warnings.map((w, i) => (
            <li key={`${i}-${w}`}>{w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
