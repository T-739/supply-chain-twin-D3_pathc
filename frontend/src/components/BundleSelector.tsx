'use client';

import { useBundleContext } from './BundleContext';
import type { BundleIndexEntry } from '@/lib/types';

function describeEntry(entry: BundleIndexEntry): string {
  const parts: string[] = [entry.bundle_id];
  if (entry.variant_set === 'b4_experiment_triplet') {
    parts.push('B4 triplet');
  } else if (entry.variant_set === 'default_3_mode') {
    parts.push('default trio');
  } else {
    parts.push(`${entry.variant_tags.length}-variant`);
  }
  if (entry.warning_count > 0) {
    parts.push(`${entry.warning_count} warning${entry.warning_count === 1 ? '' : 's'}`);
  }
  return parts.join(' · ');
}

/**
 * Global bundle selector. Rendered inside the AppShell header.
 *
 * Null-safe behavior:
 *   - while the index is loading, renders a disabled placeholder;
 *   - on error, renders the error message inline (no throw);
 *   - on empty-index, renders a "no bundles" hint and the select
 *     itself is disabled;
 *   - handles both default_3_mode and b4_experiment_triplet
 *     entries; never assumes `path_c_cold` is in the tag list.
 */
export function BundleSelector() {
  const { index, isLoading, error, selectedBundleId, setSelectedBundleId } =
    useBundleContext();

  const entries = index?.bundles ?? [];
  const hasBundles = entries.length > 0;

  return (
    <div className="bundle-selector" data-testid="bundle-selector">
      <label htmlFor="bundle-select" className="bundle-selector__label">
        Bundle
      </label>
      <select
        id="bundle-select"
        data-testid="bundle-select"
        className="bundle-selector__select"
        disabled={!hasBundles || isLoading}
        value={selectedBundleId ?? ''}
        onChange={(e) => setSelectedBundleId(e.target.value || null)}
      >
        {!hasBundles && (
          <option value="">
            {isLoading ? 'Loading…' : 'No bundles available'}
          </option>
        )}
        {hasBundles &&
          entries.map((entry) => (
            <option key={entry.bundle_id} value={entry.bundle_id}>
              {describeEntry(entry)}
            </option>
          ))}
      </select>
      {error && (
        <span className="bundle-selector__error" role="alert">
          Could not load bundle index: {error}
        </span>
      )}
    </div>
  );
}
