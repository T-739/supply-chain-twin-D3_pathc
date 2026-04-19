'use client';

import type { CompareReportRaw } from '@/lib/types';

export interface KpiMatrixViewProps {
  kpiMatrix: CompareReportRaw['kpi_matrix'];
  sessionsCompared: string[];
}

const SEGMENT_ORDER: Array<{ key: 'cold_phase' | 'warm_phase' | 'overall'; label: string }> = [
  { key: 'overall', label: 'Overall' },
  { key: 'cold_phase', label: 'Cold phase' },
  { key: 'warm_phase', label: 'Warm phase' },
];

function fmtCell(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return '—';
    return v.toFixed(4);
  }
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  return String(v);
}

/**
 * Canonical KPI matrix viewer.
 *
 * Reads only the keys the artifact already carries — does not
 * inject a synthetic KPI name, does not cross-compute cells,
 * does not reorder columns beyond the `sessionsCompared`
 * order the artifact itself committed to. An empty / missing
 * segment renders an honest "no data for this segment"
 * notice instead of a zeroed fake row set.
 */
export function KpiMatrixView({ kpiMatrix, sessionsCompared }: KpiMatrixViewProps) {
  if (!kpiMatrix) {
    return (
      <p className="compare-lab__absent" data-testid="kpi-matrix-absent">
        The compare report does not include a <code>kpi_matrix</code> block.
      </p>
    );
  }
  const modes = sessionsCompared ?? [];
  return (
    <div className="kpi-matrix" data-testid="kpi-matrix">
      {SEGMENT_ORDER.map(({ key, label }) => {
        const segment = kpiMatrix[key];
        const kpiNames = segment ? Object.keys(segment) : [];
        const hasRows = kpiNames.length > 0 && modes.length > 0;
        return (
          <section
            key={key}
            className="kpi-matrix__segment"
            data-testid={`kpi-matrix-${key}`}
            aria-label={`KPI matrix: ${label}`}
          >
            <h4 className="kpi-matrix__heading">{label}</h4>
            {!hasRows ? (
              <p className="compare-lab__absent">
                No KPI rows present for the <code>{key}</code> segment.
              </p>
            ) : (
              <div className="table-scroll">
              <table className="kpi-matrix__table">
                <thead>
                  <tr>
                    <th>KPI</th>
                    {modes.map((m) => (
                      <th key={m}>
                        <code>{m}</code>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {kpiNames.map((kpi) => (
                    <tr key={kpi} data-testid={`kpi-matrix-${key}-row-${kpi}`}>
                      <td>
                        <code>{kpi}</code>
                      </td>
                      {modes.map((m) => (
                        <td key={m}>
                          {fmtCell(
                            (segment![kpi] as Record<string, unknown> | undefined)?.[m],
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
