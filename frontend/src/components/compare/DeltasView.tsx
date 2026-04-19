'use client';

import type { CompareReportRaw } from '@/lib/types';

export interface DeltasViewProps {
  deltas: CompareReportRaw['deltas'];
}

function fmtDelta(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'null';
  if (typeof v !== 'number' || !Number.isFinite(v)) return 'null';
  return v.toFixed(4);
}

/**
 * Canonical deltas viewer.
 *
 * Renders exactly what the artifact carries — one table per
 * delta key (e.g. `path_c_cold_minus_baseline_static`),
 * showing the already-computed delta value per KPI. Nulls
 * render as the literal string "null"; we do NOT coerce them
 * to zero and we do NOT recolor deltas as good/bad. The
 * artifact is canonical; this view is just a window onto it.
 */
export function DeltasView({ deltas }: DeltasViewProps) {
  if (!deltas || Object.keys(deltas).length === 0) {
    return (
      <p className="compare-lab__absent" data-testid="deltas-absent">
        No non-baseline deltas are present on this compare report.
      </p>
    );
  }

  const deltaKeys = Object.keys(deltas).sort();

  return (
    <div className="deltas-view" data-testid="deltas-view">
      {deltaKeys.map((dk) => {
        const row = deltas[dk] ?? {};
        const kpiNames = Object.keys(row);
        return (
          <section
            key={dk}
            className="deltas-view__group"
            data-testid={`deltas-group-${dk}`}
            aria-label={`Delta group: ${dk}`}
          >
            <h4 className="deltas-view__heading">
              <code>{dk}</code>
            </h4>
            {kpiNames.length === 0 ? (
              <p className="compare-lab__absent">
                The compare report recorded the delta key but no KPI
                entries inside it.
              </p>
            ) : (
              <table className="deltas-view__table">
                <thead>
                  <tr>
                    <th>KPI</th>
                    <th>delta</th>
                  </tr>
                </thead>
                <tbody>
                  {kpiNames.map((k) => (
                    <tr
                      key={k}
                      data-testid={`deltas-row-${dk}-${k}`}
                    >
                      <td>
                        <code>{k}</code>
                      </td>
                      <td data-testid={`deltas-cell-${dk}-${k}`}>
                        {fmtDelta(row[k])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
    </div>
  );
}
