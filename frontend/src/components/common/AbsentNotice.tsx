'use client';

import type { ReactNode } from 'react';

export interface AbsentNoticeProps {
  /** Lead sentence describing what is absent. */
  children: ReactNode;
  /** Optional stable testid passthrough. */
  testid?: string;
  /**
   * Severity hint. `"info"` is the default neutral muted note;
   * `"warn"` raises the note to the warn-colored panel used by
   * the Compare Lab compare-absent / unreadable states.
   */
  tone?: 'info' | 'warn';
  /** `role="note"` is applied by default. Override if needed. */
  role?: 'note' | 'alert' | 'status';
}

/**
 * Unified absent / explanatory-note primitive.
 *
 * Every B5 page has a handful of "X is not present; here's why"
 * states (compare absent, sparse shape, B3 scope reminder, etc.).
 * Before this helper, each page expressed that state with its
 * own local markup and class name. This component consolidates
 * the visual language so state copy across pages looks and
 * sounds the same, without forcing a big refactor of every
 * page at once.
 *
 * Existing per-page absent markup continues to work — this is
 * additive.
 */
export function AbsentNotice({
  children,
  testid,
  tone = 'info',
  role = 'note',
}: AbsentNoticeProps) {
  const className =
    'absent-notice' +
    (tone === 'warn'
      ? ' absent-notice--warn'
      : ' absent-notice--info');
  return (
    <p className={className} data-testid={testid} role={role}>
      {children}
    </p>
  );
}
