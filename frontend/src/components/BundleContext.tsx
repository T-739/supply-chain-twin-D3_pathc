'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { fetchBundleIndex } from '@/lib/bff';
import type { BundleIndexEntry, BundleIndexResponse } from '@/lib/types';

/**
 * Global bundle-selection state.
 *
 * This context is the single place that talks to `/bundles`. It
 * exposes the index, the currently-selected bundle_id, and a
 * loading / error envelope. Individual pages fetch their own
 * bundle *detail* via the BFF using the selected id.
 *
 * Selection continuity:
 *   - within one SPA session, the Next.js App Router keeps this
 *     provider mounted, so switching tabs does not drop the
 *     selection;
 *   - across reloads, the selected id is mirrored to
 *     ``localStorage`` under ``LS_SELECTED_BUNDLE_ID_KEY`` and
 *     restored on next mount iff it still appears in the index;
 *   - when tests pass ``initialSelectedBundleId``, that wins and
 *     localStorage is ignored for that render.
 */

export const LS_SELECTED_BUNDLE_ID_KEY = 'b5.selectedBundleId';

function readLocalBundleId(): string | null {
  if (typeof window === 'undefined' || !window.localStorage) return null;
  try {
    const v = window.localStorage.getItem(LS_SELECTED_BUNDLE_ID_KEY);
    return typeof v === 'string' && v.length > 0 ? v : null;
  } catch {
    // Safari private mode / disabled storage → treat as unset.
    return null;
  }
}

function writeLocalBundleId(id: string | null): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    if (id) {
      window.localStorage.setItem(LS_SELECTED_BUNDLE_ID_KEY, id);
    } else {
      window.localStorage.removeItem(LS_SELECTED_BUNDLE_ID_KEY);
    }
  } catch {
    // ignore
  }
}

export interface BundleContextValue {
  index: BundleIndexResponse | null;
  isLoading: boolean;
  error: string | null;
  selectedBundleId: string | null;
  selectedEntry: BundleIndexEntry | null;
  setSelectedBundleId: (bundleId: string | null) => void;
  refresh: () => void;
}

const BundleContext = createContext<BundleContextValue | null>(null);

export interface BundleProviderProps {
  children: ReactNode;
  /**
   * Test hook: inject a fake index so tests do not need to stub
   * fetch. When provided, auto-fetch is skipped entirely.
   */
  initialIndex?: BundleIndexResponse | null;
  /** Test hook: pre-select a bundle_id. */
  initialSelectedBundleId?: string | null;
}

export function BundleProvider({
  children,
  initialIndex,
  initialSelectedBundleId,
}: BundleProviderProps) {
  const [index, setIndex] = useState<BundleIndexResponse | null>(
    initialIndex ?? null,
  );
  const [isLoading, setIsLoading] = useState<boolean>(
    initialIndex === undefined,
  );
  const [error, setError] = useState<string | null>(null);
  // When initialSelectedBundleId is explicitly provided (tests),
  // that wins. Otherwise restore from localStorage if available.
  const [selectedBundleId, setSelectedBundleIdState] = useState<
    string | null
  >(() => {
    if (initialSelectedBundleId !== undefined) {
      return initialSelectedBundleId;
    }
    return readLocalBundleId();
  });

  const setSelectedBundleId = useCallback((bundleId: string | null) => {
    setSelectedBundleIdState(bundleId);
    writeLocalBundleId(bundleId);
  }, []);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchBundleIndex();
      setIndex(response);
      // Selection precedence after a fresh index load:
      //   1. keep whatever is currently selected iff it still
      //      appears in the new index (otherwise it is stale and
      //      gets cleared so the UI does not show a phantom id);
      //   2. fall back to whatever localStorage remembers iff it
      //      still appears in the index;
      //   3. otherwise auto-select the first bundle.
      setSelectedBundleIdState((prev) => {
        const validPrev =
          prev && response.bundles.some((b) => b.bundle_id === prev);
        if (validPrev) return prev;
        const stored = readLocalBundleId();
        const validStored =
          stored && response.bundles.some((b) => b.bundle_id === stored);
        if (validStored) {
          writeLocalBundleId(stored);
          return stored;
        }
        const first = response.bundles[0];
        const fallback = first ? first.bundle_id : null;
        writeLocalBundleId(fallback);
        return fallback;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Skip auto-fetch when the caller (test) has already provided
    // an initialIndex.
    if (initialIndex !== undefined) {
      return;
    }
    void load();
  }, [initialIndex, load]);

  const selectedEntry = useMemo<BundleIndexEntry | null>(() => {
    if (!index || !selectedBundleId) return null;
    return (
      index.bundles.find((b) => b.bundle_id === selectedBundleId) ?? null
    );
  }, [index, selectedBundleId]);

  const value = useMemo<BundleContextValue>(
    () => ({
      index,
      isLoading,
      error,
      selectedBundleId,
      selectedEntry,
      setSelectedBundleId,
      refresh: () => void load(),
    }),
    [index, isLoading, error, selectedBundleId, selectedEntry, load],
  );

  return (
    <BundleContext.Provider value={value}>{children}</BundleContext.Provider>
  );
}

export function useBundleContext(): BundleContextValue {
  const ctx = useContext(BundleContext);
  if (!ctx) {
    throw new Error(
      'useBundleContext must be used within a <BundleProvider>',
    );
  }
  return ctx;
}
