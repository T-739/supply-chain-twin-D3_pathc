'use client';

import { useBundleContext } from './BundleContext';
import type { BundleIndexEntry } from '@/lib/types';

function variantSetLabel(v: BundleIndexEntry['variant_set']): string {
  if (v === 'default_3_mode') return 'Default trio';
  if (v === 'b4_experiment_triplet') return 'B4 experiment triplet';
  return 'Custom';
}

/**
 * Catalog of every bundle exposed by the BFF. Answers "where
 * could this view come from?". Selecting a row wires the rest
 * of the Overview to that bundle via the shared context.
 *
 * Empty / loading / error states are handled locally so the
 * page always renders something honest.
 */
export function BundleCatalog() {
  const { index, isLoading, error, selectedBundleId, setSelectedBundleId } =
    useBundleContext();

  return (
    <section
      className="bundle-catalog"
      data-testid="bundle-catalog"
      aria-label="Bundle catalog"
    >
      <h2 className="bundle-catalog__title">Bundle catalog</h2>
      {error && (
        <div
          className="bundle-catalog__error"
          data-testid="bundle-catalog-error"
          role="alert"
        >
          Could not load bundle index: {error}
        </div>
      )}
      {isLoading && !index && (
        <div className="bundle-catalog__loading" data-testid="bundle-catalog-loading">
          Loading bundle index…
        </div>
      )}
      {index && index.bundles.length === 0 && (
        <div
          className="bundle-catalog__empty"
          data-testid="bundle-catalog-empty"
        >
          <p>
            <strong>No evaluation bundles are available yet.</strong>
          </p>
          <p className="bundle-catalog__empty-hint">
            A bundle is produced from one full evaluation run and captures
            every session artifact, compare report, and thesis report that
            run emitted. Once a run has been bundled it will appear here and
            the rest of the surface will populate automatically. Until then,
            the identity and reproducibility sections below still describe
            the system.
          </p>
        </div>
      )}
      {index && index.bundles.length > 0 && (
        <>
          <p className="bundle-catalog__contract">
            Backend speaks bundle-contract v
            <code>{index.bundle_schema_version}</code>.
          </p>
          <table className="bundle-catalog__table" data-testid="bundle-catalog-table">
            <thead>
              <tr>
                <th>Bundle</th>
                <th>Shape</th>
                <th>Variants</th>
                <th>Reports</th>
                <th>Warnings</th>
                <th>Select</th>
              </tr>
            </thead>
            <tbody>
              {index.bundles.map((entry) => {
                const isSelected = entry.bundle_id === selectedBundleId;
                return (
                  <tr
                    key={entry.bundle_id}
                    className={
                      'bundle-catalog__row' +
                      (isSelected ? ' bundle-catalog__row--selected' : '')
                    }
                    data-testid={`bundle-row-${entry.bundle_id}`}
                  >
                    <td>
                      <code>{entry.bundle_id}</code>
                      <div className="bundle-catalog__schema-stamp">
                        schema v{entry.bundle_schema_version}
                      </div>
                    </td>
                    <td>{variantSetLabel(entry.variant_set)}</td>
                    <td>
                      <ul className="bundle-catalog__tags">
                        {entry.variant_tags.map((tag) => (
                          <li key={tag}>
                            <code>{tag}</code>
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td>
                      <div>
                        compare:{' '}
                        <strong>
                          {entry.has_compare_report ? 'present' : 'absent'}
                        </strong>
                      </div>
                      <div>
                        thesis:{' '}
                        <strong>
                          {entry.has_thesis_report ? 'present' : 'absent'}
                        </strong>
                      </div>
                    </td>
                    <td>{entry.warning_count}</td>
                    <td>
                      <button
                        type="button"
                        disabled={isSelected}
                        onClick={() => setSelectedBundleId(entry.bundle_id)}
                        data-testid={`select-${entry.bundle_id}`}
                      >
                        {isSelected ? 'Selected' : 'Select'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
