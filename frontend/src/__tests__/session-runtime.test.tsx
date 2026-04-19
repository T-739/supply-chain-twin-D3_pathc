import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { AppShell } from '@/components/AppShell';
import { SessionRuntimePage } from '@/components/SessionRuntimePage';

import {
  b4AgentVisibleArtifact,
  b4BundleDetail,
  defaultBaselineArtifact,
  defaultBundleDetail,
  defaultSessionArtifact,
  emptyIndex,
  fullIndex,
  unloadableArtifact,
  zeroEventArtifact,
} from './fixtures';
import { artifactKey, installBffFetchMock } from './testHelpers';

describe('Session Runtime page', () => {
  describe('default trio bundle', () => {
    beforeEach(() => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
        },
        sessionArtifactsByKey: {
          [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
            defaultBaselineArtifact,
          [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]: {
            ...defaultSessionArtifact,
            variant_tag: 'path_c_cold',
            session_artifact_raw: {
              ...defaultSessionArtifact.session_artifact_raw!,
              config: { mode: 'PATH_C_COLD' },
            },
          },
          [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
            defaultSessionArtifact,
        },
      });
    });

    it('loads as a real page and renders the three-layer event detail', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <SessionRuntimePage />
        </AppShell>,
      );

      expect(screen.getByTestId('session-runtime-page')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Session Runtime', level: 1 }))
        .toBeInTheDocument();

      // Focus selector populates with all three default-trio tags.
      await waitFor(() => {
        const focus = screen.getByTestId('session-focus-select') as HTMLSelectElement;
        const optionValues = Array.from(focus.options).map((o) => o.value);
        expect(optionValues).toEqual([
          'baseline_static',
          'path_c_cold',
          'path_c_warm',
        ]);
      });

      // Auto-focuses the first tag.
      await waitFor(() => {
        expect(screen.getByTestId('header-focus-tag')).toHaveTextContent(
          'baseline_static',
        );
      });

      // Event list renders and auto-selects event 0 → detail shows.
      await waitFor(() => {
        expect(screen.getByTestId('event-list')).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(screen.getByTestId('event-detail')).toBeInTheDocument();
      });

      // Three-layer structure present.
      expect(screen.getByTestId('event-detail-path-b')).toBeInTheDocument();
      expect(screen.getByTestId('event-detail-path-c')).toBeInTheDocument();
      expect(screen.getByTestId('event-detail-extensions')).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'Path B raw', level: 4 }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'Path C overlay', level: 4 }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: 'Extensions', level: 4 }),
      ).toBeInTheDocument();

      // B4 is always labeled not-surfaced-at-event-level, regardless of bundle.
      expect(screen.getByTestId('ext-b4-presence')).toHaveTextContent(
        /not surfaced at event level/,
      );
    });

    it('updates the event detail when a different event is selected', async () => {
      const user = userEvent.setup();
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <SessionRuntimePage />
        </AppShell>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('event-detail')).toBeInTheDocument();
      });
      // Event 0 is auto-selected (3B: "Event 1 of N" label).
      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
        /Event 1 of 2/,
      );
      // Switch to event 1.
      await user.click(screen.getByTestId('select-event-1'));
      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
          /Event 2 of 2/,
        );
      });
    });
  });

  describe('B4 triplet bundle', () => {
    beforeEach(() => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          [b4BundleDetail.metadata.bundle_id]: b4BundleDetail,
        },
        sessionArtifactsByKey: {
          [artifactKey(
            'fixture_b4_triplet_v1',
            'path_c_warm_agent_visible_memory',
          )]: b4AgentVisibleArtifact,
          [artifactKey('fixture_b4_triplet_v1', 'baseline_static')]: {
            ...defaultBaselineArtifact,
            bundle_id: 'fixture_b4_triplet_v1',
            variant_tag: 'baseline_static',
          },
          [artifactKey(
            'fixture_b4_triplet_v1',
            'path_c_warm_policy_only',
          )]: {
            ...defaultSessionArtifact,
            bundle_id: 'fixture_b4_triplet_v1',
            variant_tag: 'path_c_warm_policy_only',
          },
        },
      });
    });

    it('renders without assuming path_c_cold exists', async () => {
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <SessionRuntimePage />
        </AppShell>,
      );

      await waitFor(() => {
        const focus = screen.getByTestId('session-focus-select') as HTMLSelectElement;
        const optionValues = Array.from(focus.options).map((o) => o.value);
        expect(optionValues).toEqual([
          'baseline_static',
          'path_c_warm_policy_only',
          'path_c_warm_agent_visible_memory',
        ]);
        expect(optionValues).not.toContain('path_c_cold');
      });
    });

    it('switching to the agent-visible variant surfaces the overlay extension presence', async () => {
      const user = userEvent.setup();
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_b4_triplet_v1"
        >
          <SessionRuntimePage />
        </AppShell>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('event-list')).toBeInTheDocument();
      });

      // Change focus to the agent-visible variant.
      const select = screen.getByTestId('session-focus-select') as HTMLSelectElement;
      await user.selectOptions(select, 'path_c_warm_agent_visible_memory');

      await waitFor(() => {
        expect(screen.getByTestId('header-focus-tag')).toHaveTextContent(
          'path_c_warm_agent_visible_memory',
        );
      });

      // Event 1 has correlation + replan overlays. Select it.
      await waitFor(() => {
        expect(screen.getByTestId('event-row-1')).toBeInTheDocument();
      });
      await user.click(screen.getByTestId('select-event-1'));
      await waitFor(() => {
        expect(screen.getByTestId('ext-b2-presence')).toHaveTextContent(
          'present',
        );
      });
      expect(screen.getByTestId('ext-b1-presence')).toHaveTextContent('present');

      // B4 presence always says "not surfaced at event level" —
      // B4 stays compare-only even on the agent-visible variant.
      expect(screen.getByTestId('ext-b4-presence')).toHaveTextContent(
        /not surfaced at event level/,
      );
    });
  });

  describe('honest state handling', () => {
    it('renders a no-bundle notice when nothing is selected', () => {
      installBffFetchMock({ index: emptyIndex });
      render(
        <AppShell initialIndex={emptyIndex}>
          <SessionRuntimePage />
        </AppShell>,
      );
      expect(screen.getByTestId('runtime-no-bundle')).toBeInTheDocument();
      // Focus selector is disabled.
      expect(screen.getByTestId('session-focus-select')).toBeDisabled();
    });

    it('renders a zero-events notice when the session has no events', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
        },
        sessionArtifactsByKey: {
          [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
            zeroEventArtifact,
          [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
            zeroEventArtifact,
          [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
            zeroEventArtifact,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <SessionRuntimePage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('event-list-empty')).toBeInTheDocument();
      });
      // No detail is shown because there is no event to select.
      expect(screen.queryByTestId('event-detail')).toBeNull();
    });

    it('renders an unloadable-artifact notice without crashing', async () => {
      installBffFetchMock({
        index: fullIndex,
        detailsByBundleId: {
          [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
        },
        sessionArtifactsByKey: {
          [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
            unloadableArtifact,
          [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
            unloadableArtifact,
          [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
            unloadableArtifact,
        },
      });
      render(
        <AppShell
          initialIndex={fullIndex}
          initialSelectedBundleId="fixture_default_3mode_v1"
        >
          <SessionRuntimePage />
        </AppShell>,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId('runtime-artifact-unloadable'),
        ).toBeInTheDocument();
      });
      // Summary strip surfaces the load warning.
      const warnings = screen.getByTestId('summary-load-warnings');
      expect(within(warnings).getByText(/unreadable/)).toBeInTheDocument();
      // No event list and no event detail are rendered.
      expect(screen.queryByTestId('event-list')).toBeNull();
      expect(screen.queryByTestId('event-detail')).toBeNull();
    });
  });
});
