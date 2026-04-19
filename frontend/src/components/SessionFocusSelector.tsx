'use client';

import type { BundleDetailResponse } from '@/lib/types';

export interface SessionFocusSelectorProps {
  bundleDetail: BundleDetailResponse | null;
  focusedTag: string | null;
  onFocusChange: (tag: string | null) => void;
}

/**
 * Session Focus Selector — pick a variant tag within the
 * currently selected bundle. Rendered inside the Session
 * Runtime page, below the global AppShell's bundle selector.
 *
 * Null-safety:
 *   - no bundle detail yet → disabled with a neutral hint
 *   - bundle has zero variants → disabled with an explicit
 *     "no sessions" hint
 *   - works identically for default_3_mode and
 *     b4_experiment_triplet; does NOT reference `path_c_cold`.
 */
export function SessionFocusSelector({
  bundleDetail,
  focusedTag,
  onFocusChange,
}: SessionFocusSelectorProps) {
  const tags = bundleDetail?.metadata.variant_tags ?? [];
  const hasBundle = bundleDetail !== null;
  const hasSessions = tags.length > 0;

  return (
    <div
      className="session-focus-selector"
      data-testid="session-focus-selector"
    >
      <label
        htmlFor="session-focus-select"
        className="session-focus-selector__label"
      >
        Session focus
      </label>
      <select
        id="session-focus-select"
        data-testid="session-focus-select"
        className="session-focus-selector__select"
        disabled={!hasBundle || !hasSessions}
        value={focusedTag ?? ''}
        onChange={(e) => onFocusChange(e.target.value || null)}
      >
        {!hasBundle && <option value="">Select a bundle first</option>}
        {hasBundle && !hasSessions && (
          <option value="">No sessions in this bundle</option>
        )}
        {hasBundle &&
          hasSessions &&
          tags.map((tag) => {
            const summary = bundleDetail!.sessions.find(
              (s) => s.variant_tag === tag,
            );
            const mode = summary?.mode ?? '?';
            return (
              <option key={tag} value={tag}>
                {tag} · {mode}
              </option>
            );
          })}
      </select>
    </div>
  );
}
