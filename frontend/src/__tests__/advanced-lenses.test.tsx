import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { AdvancedLensesPage } from '@/components/AdvancedLensesPage';

import {
  b4BundleDetailWithCompare,
  bundleDetailCompareUnreadable,
  bundleDetailNoCompare,
  defaultBundleDetailWithCompare,
  defaultBundleDetailWithLenses,
  emptyIndex,
  fullIndex,
  sparseCompareBundleDetail,
} from './fixtures';
import { installBffFetchMock } from './testHelpers';

describe('Advanced Lenses route', () => {
  describe('default trio with all sibling blocks', () => {
    beforeEach(() => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': defaultBundleDetailWithLenses,
        },
      });
    });

    it('loads as a real page and populates B1 / B2 / B3 lenses', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      expect(screen.getByTestId('advanced-lenses-page')).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'Advanced Lenses', level: 1 }),
      ).toBeInTheDocument();

      // B1 replan lens
      await waitFor(() => {
        expect(screen.getByTestId('replan-lens')).toBeInTheDocument();
      });
      expect(screen.getByTestId('replan-lens-total')).toHaveTextContent('2');
      expect(
        screen.getByTestId('replan-lens-row-path_c_warm'),
      ).toHaveTextContent('0.5000'); // replan_recovery_rate
      // Trigger-type table carries the counts per trigger (1 for
      // COST_DEVIATION + 1 for EXECUTION_FAILED → 2 non-zero cells).
      const triggerTable = screen.getByTestId(
        'replan-lens-trigger-table',
      );
      expect(
        within(triggerTable).getByRole('columnheader', {
          name: 'COST_DEVIATION',
        }),
      ).toBeInTheDocument();

      // B2 correlator lens
      expect(screen.getByTestId('correlation-lens')).toBeInTheDocument();
      expect(
        screen.getByTestId('correlation-lens-row-path_c_warm'),
      ).toHaveTextContent('4'); // total_signals
      expect(
        screen.getByTestId('correlation-lens-pattern-row-ETA_PATH_COMPOUND'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('correlation-lens-event-ids')).toHaveTextContent(
        'EV-004',
      );

      // B3 cumulative memory lens
      expect(screen.getByTestId('cumulative-lens')).toBeInTheDocument();
      expect(
        screen.getByTestId('cumulative-lens-scope-label'),
      ).toHaveTextContent(/session\s*\/\s*compare-level/);
      const row = screen.getByTestId('cumulative-lens-row-path_c_warm');
      expect(row).toHaveTextContent('FIXTURE-DEFAULT-PATH_C_WARM');
      expect(row).toHaveTextContent('PRIOR-SESSION-A');
      expect(
        screen.getByTestId('cumulative-lens-prior-row-PRIOR-SESSION-A'),
      ).toHaveTextContent('3');

      // Raw JSON fallback exists for at least one populated lens.
      expect(screen.getByTestId('replan-lens-raw-json')).toBeInTheDocument();
      expect(
        screen.getByTestId('correlation-lens-raw-json'),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('cumulative-lens-raw-json'),
      ).toBeInTheDocument();
    });

    it('B4 lens is present-absent but still carries the experiment ribbon', async () => {
      // This default-trio fixture does NOT include
      // agent_memory_experiment_summary, so the B4 lens must
      // render its *absent* state — and the experiment framing
      // labels must still appear.
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('agent-memory-lens')).toBeInTheDocument();
      });
      // Absent state of B4 from CompareLab's reused block.
      const b4 = screen.getByTestId('agent-memory-lens');
      expect(
        within(b4).getByTestId('b4-experiment-absent'),
      ).toBeInTheDocument();
      const labels = within(b4).getByTestId('b4-experiment-labels');
      expect(labels).toHaveTextContent('experiment');
      expect(labels).toHaveTextContent('default-off');
      expect(labels).toHaveTextContent('compare-only');
    });
  });

  describe('B4 triplet — only B4 block present', () => {
    beforeEach(() => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_b4_triplet_v1': b4BundleDetailWithCompare,
        },
      });
    });

    it('renders without assuming path_c_cold exists', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('lenses-variant-set')).toHaveTextContent(
          'b4_experiment_triplet',
        );
      });
      // path_c_cold must not appear inside any lens block as if
      // it were a session tag. (It DOES appear in the
      // bundle-level warnings panel, which is the metadata
      // statement that path_c_cold is intentionally absent —
      // that warning is user-facing reassurance, not a
      // fabricated session tag.)
      for (const testId of [
        'replan-lens-absent',
        'correlation-lens-absent',
        'cumulative-lens-absent',
        'agent-memory-lens',
      ]) {
        const node = screen.getByTestId(testId);
        expect(node.textContent ?? '').not.toMatch(/path_c_cold/);
      }
    });

    it('renders the B4 experiment lens populated + other lenses as absent', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('agent-memory-lens')).toBeInTheDocument();
      });
      const b4 = screen.getByTestId('agent-memory-lens');
      expect(within(b4).getByTestId('b4-experiment')).toBeInTheDocument();
      const labels = within(b4).getByTestId('b4-experiment-labels');
      expect(labels).toHaveTextContent('experiment');
      expect(labels).toHaveTextContent('default-off');
      expect(labels).toHaveTextContent('compare-only');
      // Other lenses render their honest-absent state.
      expect(screen.getByTestId('replan-lens-absent')).toBeInTheDocument();
      expect(
        screen.getByTestId('correlation-lens-absent'),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('cumulative-lens-absent'),
      ).toBeInTheDocument();
    });

    it('B4 variant tags show the triplet but no path_c_cold', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId('b4-experiment-variant-tags'),
        ).toBeInTheDocument();
      });
      const tags = screen.getByTestId('b4-experiment-variant-tags');
      expect(tags).toHaveTextContent('baseline_static');
      expect(tags).toHaveTextContent('path_c_warm_policy_only');
      expect(tags).toHaveTextContent('path_c_warm_agent_visible_memory');
      expect(tags).not.toHaveTextContent('path_c_cold');
    });
  });

  describe('honest state handling', () => {
    it('renders a no-bundle notice when nothing is selected', () => {
      installBffFetchMock({ index: emptyIndex });
      render(
        <AppShell initialIndex={emptyIndex}>
          <AdvancedLensesPage />
        </AppShell>,
      );
      expect(screen.getByTestId('lenses-no-bundle')).toBeInTheDocument();
    });

    it('handles compare-absent metadata honestly', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': bundleDetailNoCompare,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId('lenses-compare-absent'),
        ).toBeInTheDocument();
      });
      // None of the lens blocks are rendered when compare is absent.
      expect(screen.queryByTestId('replan-lens')).toBeNull();
      expect(screen.queryByTestId('replan-lens-absent')).toBeNull();
      expect(screen.queryByTestId('agent-memory-lens')).toBeNull();
    });

    it('handles compare-claimed-but-unreadable honestly', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': bundleDetailCompareUnreadable,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId('lenses-compare-unreadable'),
        ).toBeInTheDocument();
      });
      // Warnings surface.
      expect(screen.getByTestId('lenses-warnings')).toBeInTheDocument();
    });

    it('handles compare present but with no sibling blocks', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': defaultBundleDetailWithCompare,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId('lenses-no-sibling-blocks'),
        ).toBeInTheDocument();
      });
      // All four lenses render their honest-absent state.
      expect(screen.getByTestId('replan-lens-absent')).toBeInTheDocument();
      expect(
        screen.getByTestId('correlation-lens-absent'),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('cumulative-lens-absent'),
      ).toBeInTheDocument();
      const b4 = screen.getByTestId('agent-memory-lens');
      expect(
        within(b4).getByTestId('b4-experiment-absent'),
      ).toBeInTheDocument();
    });

    it('survives a sparse compare shape without crashing', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': sparseCompareBundleDetail,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('advanced-lenses-page')).toBeInTheDocument();
      });
      // All lens blocks render absent state without throwing.
      expect(
        screen.getByTestId('lenses-no-sibling-blocks'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('replan-lens-absent')).toBeInTheDocument();
      expect(
        screen.getByTestId('correlation-lens-absent'),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('cumulative-lens-absent'),
      ).toBeInTheDocument();
    });
  });

  describe('B3 summary-level framing', () => {
    it('cumulative lens always carries the session/compare-level scope label', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': defaultBundleDetailWithLenses,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <AdvancedLensesPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('cumulative-lens')).toBeInTheDocument();
      });
      const label = screen.getByTestId('cumulative-lens-scope-label');
      expect(label).toHaveTextContent(/session\s*\/\s*compare-level/);
      // The lens copy explicitly distances itself from per-event
      // semantics.
      const cumLens = screen.getByTestId('cumulative-lens');
      expect(cumLens.textContent ?? '').toMatch(
        /does not (?:and cannot )?attribute cumulative memory to individual events/,
      );
    });
  });
});
