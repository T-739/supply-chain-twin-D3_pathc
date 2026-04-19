import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { CompareLabPage } from '@/components/CompareLabPage';

import {
  b4BundleDetailWithCompare,
  bundleDetailCompareUnreadable,
  bundleDetailNoCompare,
  defaultBundleDetailWithCompare,
  emptyIndex,
  fullIndex,
  sparseCompareBundleDetail,
} from './fixtures';
import { installBffFetchMock } from './testHelpers';

describe('Compare Lab route', () => {
  describe('default trio bundle', () => {
    beforeEach(() => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          'fixture_default_3mode_v1': defaultBundleDetailWithCompare,
        },
      });
    });

    it('loads as a real page with KPI matrix, deltas, thesis section', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <CompareLabPage />
        </AppShell>,
      );
      expect(screen.getByTestId('compare-lab-page')).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'Compare Lab', level: 1 }),
      ).toBeInTheDocument();

      // Header facts populated from metadata + compare.
      await waitFor(() => {
        expect(screen.getByTestId('compare-variant-set')).toHaveTextContent(
          'default_3_mode',
        );
      });
      expect(screen.getByTestId('compare-has-compare')).toHaveTextContent(
        /present/,
      );
      expect(screen.getByTestId('compare-has-thesis')).toHaveTextContent(
        /present/,
      );
      expect(screen.getByTestId('compare-schema-version')).toHaveTextContent(
        'v1.1',
      );
      expect(screen.getByTestId('compare-baseline-mode')).toHaveTextContent(
        'baseline_static',
      );

      // KPI matrix: overall segment renders canonical KPI rows.
      const matrix = screen.getByTestId('kpi-matrix');
      expect(matrix).toBeInTheDocument();
      const overallSeg = screen.getByTestId('kpi-matrix-overall');
      expect(
        within(overallSeg).getByTestId(
          'kpi-matrix-overall-row-sla_preservation_rate',
        ),
      ).toHaveTextContent('0.8200');
      expect(
        within(overallSeg).getByTestId(
          'kpi-matrix-overall-row-calibrated_autonomy_score',
        ),
      ).toHaveTextContent('0.6200');

      // Deltas render a group per non-baseline mode.
      expect(
        screen.getByTestId(
          'deltas-group-path_c_cold_minus_baseline_static',
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(
          'deltas-group-path_c_warm_minus_baseline_static',
        ),
      ).toBeInTheDocument();
      // Null delta renders literally as "null".
      expect(
        screen.getByTestId(
          'deltas-cell-path_c_warm_minus_baseline_static-known_outcome_coverage',
        ),
      ).toHaveTextContent('null');

      // Diverged events show identifying info + adjustment ref.
      expect(screen.getByTestId('diverged-events')).toBeInTheDocument();
      expect(screen.getByTestId('diverged-events-item-0')).toHaveTextContent(
        'EV-003',
      );
      expect(
        screen.getByTestId('diverged-events-adjustment-0'),
      ).toHaveTextContent('UPGRADE_ONE_LEVEL');

      // Thesis section carries structured claim support + raw markdown.
      expect(screen.getByTestId('thesis-claim-support')).toBeInTheDocument();
      expect(screen.getByTestId('thesis-claim-supports')).toHaveTextContent(
        'true',
      );
      expect(screen.getByTestId('thesis-markdown')).toHaveTextContent(
        /Path C Phase 3 — Thesis-Aligned Session Compare Report/,
      );

      // Raw compare JSON fallback is available.
      expect(screen.getByTestId('compare-raw-json')).toBeInTheDocument();
    });

    it('does not promote B4 — absent state renders the isolated experiment panel', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('b4-experiment-absent')).toBeInTheDocument();
      });
      // Even in absence, the experiment framing labels are present.
      const labels = screen.getByTestId('b4-experiment-labels');
      expect(labels).toHaveTextContent('experiment');
      expect(labels).toHaveTextContent('default-off');
      expect(labels).toHaveTextContent('compare-only');
    });
  });

  describe('B4 triplet bundle', () => {
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
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('compare-variant-set')).toHaveTextContent(
          'b4_experiment_triplet',
        );
      });
      // sessions_compared is the B4 triplet — path_c_cold is absent.
      const sc = screen.getByTestId('compare-sessions-compared');
      expect(sc).toHaveTextContent('baseline_static');
      expect(sc).toHaveTextContent('path_c_warm_policy_only');
      expect(sc).toHaveTextContent('path_c_warm_agent_visible_memory');
      expect(sc).not.toHaveTextContent('path_c_cold');
      // KPI matrix headers also avoid path_c_cold.
      const matrix = screen.getByTestId('kpi-matrix');
      expect(matrix).not.toHaveTextContent('path_c_cold');
    });

    it('surfaces the B4 block with experiment/default-off/compare-only labels', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('b4-experiment')).toBeInTheDocument();
      });
      const labels = screen.getByTestId('b4-experiment-labels');
      expect(labels).toHaveTextContent('experiment');
      expect(labels).toHaveTextContent('default-off');
      expect(labels).toHaveTextContent('compare-only');
      // Structural fields surface.
      expect(screen.getByTestId('b4-experiment-schema')).toHaveTextContent(
        'v1.0',
      );
      const variantTags = screen.getByTestId('b4-experiment-variant-tags');
      expect(variantTags).toHaveTextContent(
        'path_c_warm_agent_visible_memory',
      );
      // Session-id map + diverged ids.
      expect(
        screen.getByTestId(
          'b4-experiment-row-path_c_warm_agent_visible_memory',
        ),
      ).toHaveTextContent('FIXTURE-B4-PATH_C_WARM_AGENT_VISIBLE_MEMORY');
      expect(screen.getByTestId('b4-experiment-diverged')).toHaveTextContent(
        'EV-007',
      );
      // Raw experiment JSON fallback.
      expect(screen.getByTestId('b4-experiment-raw-json')).toBeInTheDocument();
    });

    it('keeps B4 outside the mainline KPI matrix', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('kpi-matrix')).toBeInTheDocument();
      });
      // The KPI matrix must NOT contain the B4 labels themselves —
      // labels live inside the experiment block.
      const matrix = screen.getByTestId('kpi-matrix');
      expect(matrix.textContent ?? '').not.toMatch(/experiment/);
      expect(matrix.textContent ?? '').not.toMatch(/default-off/);
      expect(matrix.textContent ?? '').not.toMatch(/compare-only/);
      // The mainline compare thesis section still renders.
      expect(screen.getByTestId('thesis-section')).toBeInTheDocument();
    });
  });

  describe('honest state handling', () => {
    it('renders a no-bundle notice when nothing is selected', () => {
      installBffFetchMock({ index: emptyIndex });
      render(
        <AppShell initialIndex={emptyIndex}>
          <CompareLabPage />
        </AppShell>,
      );
      expect(screen.getByTestId('compare-no-bundle')).toBeInTheDocument();
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
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('compare-absent')).toBeInTheDocument();
      });
      // Mainline compare surfaces are not rendered.
      expect(screen.queryByTestId('kpi-matrix')).toBeNull();
      expect(screen.queryByTestId('deltas-view')).toBeNull();
      expect(screen.queryByTestId('compare-raw-json')).toBeNull();
      // Thesis section still renders — with its own "thesis absent" notice.
      expect(screen.getByTestId('thesis-section')).toBeInTheDocument();
      expect(
        screen.getByTestId('thesis-markdown-absent-metadata'),
      ).toBeInTheDocument();
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
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId('compare-raw-unreadable'),
        ).toBeInTheDocument();
      });
      // Load warnings are surfaced prominently.
      const warnings = screen.getByTestId('compare-warnings');
      expect(within(warnings).getByText(/compare_report\.json is missing/))
        .toBeInTheDocument();
      expect(within(warnings).getByText(/thesis_report\.md is missing/))
        .toBeInTheDocument();
      // Thesis section renders its own unreadable state.
      expect(
        screen.getByTestId('thesis-markdown-unreadable'),
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
          <CompareLabPage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('compare-lab-page')).toBeInTheDocument();
      });
      // Schema v0.9 surfaces honestly.
      expect(screen.getByTestId('compare-schema-version')).toHaveTextContent(
        'v0.9',
      );
      // Each optional section has its own honest-absent state.
      expect(screen.getByTestId('kpi-matrix-absent')).toBeInTheDocument();
      expect(screen.getByTestId('deltas-absent')).toBeInTheDocument();
      expect(screen.getByTestId('diverged-events-empty')).toBeInTheDocument();
      expect(
        screen.getByTestId('thesis-claim-support-absent'),
      ).toBeInTheDocument();
      // B4 block still renders (absent state).
      expect(screen.getByTestId('b4-experiment-absent')).toBeInTheDocument();
      // Raw compare JSON remains available.
      expect(screen.getByTestId('compare-raw-json')).toBeInTheDocument();
    });
  });
});
