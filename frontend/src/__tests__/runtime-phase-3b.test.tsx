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
  divergedArtifact,
  emptyIndex,
  fullIndex,
  unloadableArtifact,
  withMemorySnapshotArtifact,
} from './fixtures';
import { artifactKey, installBffFetchMock } from './testHelpers';

describe('Phase 3B · structured overlay', () => {
  it('renders governance truth and effective decision as distinct tracks', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
      },
      sessionArtifactsByKey: {
        [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
          defaultBaselineArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
          defaultSessionArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
          defaultSessionArtifact,
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
      expect(screen.getByTestId('overlay-panel')).toBeInTheDocument();
    });

    // Dual-track containers exist and are distinct.
    const gt = screen.getByTestId('overlay-governance-truth');
    const ed = screen.getByTestId('overlay-effective-decision');
    expect(gt).toBeInTheDocument();
    expect(ed).toBeInTheDocument();
    expect(gt).not.toBe(ed);

    // Governance truth carries risk_level + recommended_candidate_type.
    expect(within(gt).getByTestId('gt-risk-level')).toHaveTextContent('MEDIUM');
    expect(within(gt).getByTestId('gt-recommended-candidate-type'))
      .toHaveTextContent('EXPEDITE');

    // Effective decision carries route / action / status / effective_risk.
    expect(within(ed).getByTestId('ed-final-route')).toHaveTextContent(
      'AUTO_EXECUTE',
    );
    expect(within(ed).getByTestId('ed-action-taken')).toHaveTextContent(
      'EXPEDITE',
    );
    expect(within(ed).getByTestId('ed-execution-status')).toHaveTextContent(
      'executed',
    );
    expect(within(ed).getByTestId('ed-effective-risk')).toHaveTextContent(
      'MEDIUM',
    );

    // Adjustment panel explicitly reports the absent case.
    expect(screen.getByTestId('overlay-adjustment-absent')).toBeInTheDocument();

    // Raw overlay JSON fallback is collapsed but present.
    expect(screen.getByTestId('overlay-raw-json')).toBeInTheDocument();
  });

  it('flags divergence between governance truth and effective decision', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
      },
      sessionArtifactsByKey: {
        [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
          divergedArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
          divergedArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
          divergedArtifact,
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
      expect(screen.getByTestId('overlay-divider')).toHaveTextContent(
        'diverged',
      );
    });
    // The two tracks carry different risk values.
    expect(screen.getByTestId('gt-risk-level')).toHaveTextContent('MEDIUM');
    expect(screen.getByTestId('ed-effective-risk')).toHaveTextContent('LOW');
    // Adjustment is structured, not just raw JSON.
    expect(screen.getByTestId('adj-rule-id')).toHaveTextContent(
      'R-AUTOEXPEDITE-LOW',
    );
    expect(screen.getByTestId('adj-adjustment-type')).toHaveTextContent(
      'UPGRADE_ONE_LEVEL',
    );
    expect(screen.getByTestId('adj-pre-adjustment-risk')).toHaveTextContent(
      'MEDIUM',
    );
    expect(screen.getByTestId('adj-post-adjustment-risk')).toHaveTextContent(
      'LOW',
    );
  });
});

describe('Phase 3B · structured extensions', () => {
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
        [artifactKey('fixture_b4_triplet_v1', 'path_c_warm_policy_only')]: {
          ...defaultSessionArtifact,
          bundle_id: 'fixture_b4_triplet_v1',
          variant_tag: 'path_c_warm_policy_only',
        },
      },
    });
  });

  it('renders B1 replan trace as a structured table when present', async () => {
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

    const select = screen.getByTestId(
      'session-focus-select',
    ) as HTMLSelectElement;
    await user.selectOptions(select, 'path_c_warm_agent_visible_memory');
    await waitFor(() => {
      expect(screen.getByTestId('event-row-1')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('select-event-1'));

    await waitFor(() => {
      expect(screen.getByTestId('ext-b1-trace-table')).toBeInTheDocument();
    });
    // Structural row with the trigger_type pulled from the
    // nested trigger object.
    expect(screen.getByTestId('ext-b1-trace-row-0')).toHaveTextContent(
      'NO_TRIGGER',
    );
    // Raw JSON remains available as a collapsible fallback.
    expect(screen.getByTestId('ext-b1-trace-json')).toBeInTheDocument();
  });

  it('renders B2 correlation_context metadata and signals state', async () => {
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
    const select = screen.getByTestId(
      'session-focus-select',
    ) as HTMLSelectElement;
    await user.selectOptions(select, 'path_c_warm_agent_visible_memory');
    await waitFor(() => {
      expect(screen.getByTestId('event-row-1')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('select-event-1'));

    await waitFor(() => {
      expect(screen.getByTestId('ext-b2-presence')).toHaveTextContent(
        'present',
      );
    });
    expect(screen.getByTestId('ext-b2-window-size')).toHaveTextContent('3');
    expect(screen.getByTestId('ext-b2-window-events')).toHaveTextContent('0');
    expect(screen.getByTestId('ext-b2-signals-count')).toHaveTextContent('0');
    // "Ran but matched nothing" is its own explicit state.
    expect(screen.getByTestId('ext-b2-empty-signals')).toBeInTheDocument();
  });

  it('shows B1/B2 as absent on the default-trio baseline variant', async () => {
    // Default-trio fixtures carry no replan or correlation data
    // — the extensions panel must say "absent" for both, not
    // fabricate structural content.
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
      },
      sessionArtifactsByKey: {
        [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
          defaultBaselineArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
          defaultSessionArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
          defaultSessionArtifact,
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
      expect(screen.getByTestId('ext-b1-presence')).toHaveTextContent('absent');
    });
    expect(screen.getByTestId('ext-b1-triggers-presence')).toHaveTextContent(
      'absent',
    );
    expect(screen.getByTestId('ext-b2-presence')).toHaveTextContent('absent');
    // No structural tables are rendered when absent.
    expect(screen.queryByTestId('ext-b1-trace-table')).toBeNull();
    expect(screen.queryByTestId('ext-b2-signals-table')).toBeNull();
  });

  it('keeps B3 session-level: no per-event B3 panel is fabricated', async () => {
    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId="fixture_b4_triplet_v1"
      >
        <SessionRuntimePage />
      </AppShell>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('ext-b3-block')).toBeInTheDocument();
    });
    // Always "not surfaced at event level" — regardless of bundle.
    expect(screen.getByTestId('ext-b3-presence')).toHaveTextContent(
      /not surfaced at event level/,
    );
    // The explanatory note points at session-level provenance.
    expect(screen.getByTestId('ext-b3-block')).toHaveTextContent(
      /session-level/,
    );
  });

  it('keeps B4 labeled experiment / default-off / compare-only', async () => {
    const user = userEvent.setup();
    render(
      <AppShell
        initialIndex={fullIndex}
        initialSelectedBundleId="fixture_b4_triplet_v1"
      >
        <SessionRuntimePage />
      </AppShell>,
    );
    // Focus agent-visible variant — the one a naive reader
    // might expect to "light up" B4.
    await waitFor(() => {
      expect(screen.getByTestId('event-list')).toBeInTheDocument();
    });
    const select = screen.getByTestId(
      'session-focus-select',
    ) as HTMLSelectElement;
    await user.selectOptions(select, 'path_c_warm_agent_visible_memory');
    await waitFor(() => {
      expect(screen.getByTestId('event-row-0')).toBeInTheDocument();
    });

    const b4Block = screen.getByTestId('ext-b4-block');
    expect(within(b4Block).getByTestId('ext-b4-presence')).toHaveTextContent(
      /not surfaced at event level/,
    );
    const labels = within(b4Block).getByTestId('ext-b4-labels');
    expect(labels).toHaveTextContent('experiment');
    expect(labels).toHaveTextContent('default-off');
    expect(labels).toHaveTextContent('compare-only');
    // Confirm the B4 block stays outside the per-event data
    // layer (no JSON dump from the event record).
    expect(
      within(b4Block).queryByTestId('event-detail-path-b-json'),
    ).toBeNull();
  });
});

describe('Phase 3B · summary strip deepened', () => {
  it('shows route/action mix, schema_versions, and memory row count', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
      },
      sessionArtifactsByKey: {
        [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
          withMemorySnapshotArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
          withMemorySnapshotArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
          defaultSessionArtifact,
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
    // baseline_static is auto-focused; it uses withMemorySnapshot.
    await waitFor(() => {
      expect(screen.getByTestId('summary-memory-rows')).toHaveTextContent('3');
    });
    expect(screen.getByTestId('summary-route-mix')).toHaveTextContent(
      'AUTO_EXECUTE',
    );
    expect(screen.getByTestId('summary-action-mix')).toHaveTextContent(
      'EXPEDITE',
    );
  });

  it('exposes schema_versions when the artifact carries it', async () => {
    installBffFetchMock({
      index: fullIndex,
      detailsByBundleId: {
        [defaultBundleDetail.metadata.bundle_id]: defaultBundleDetail,
      },
      sessionArtifactsByKey: {
        [artifactKey('fixture_default_3mode_v1', 'baseline_static')]:
          defaultSessionArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_cold')]:
          defaultSessionArtifact,
        [artifactKey('fixture_default_3mode_v1', 'path_c_warm')]:
          defaultSessionArtifact,
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
      const block = screen.getByTestId('summary-schema-versions');
      expect(block).toHaveTextContent('session_artifact');
      expect(block).toHaveTextContent('v1.0');
      expect(block).toHaveTextContent('session_event_record');
      expect(block).toHaveTextContent('v1.2');
    });
  });
});

describe('Phase 3B · event detail navigation', () => {
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
        [artifactKey('fixture_b4_triplet_v1', 'baseline_static')]:
          b4AgentVisibleArtifact,
        [artifactKey('fixture_b4_triplet_v1', 'path_c_warm_policy_only')]:
          b4AgentVisibleArtifact,
      },
    });
  });

  it('prev/next buttons move through the event stream honestly', async () => {
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
      expect(screen.getByTestId('event-detail')).toBeInTheDocument();
    });
    // Auto-selected: event 1 of 3.
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
      /Event 1 of 3/,
    );
    // Prev is disabled at the boundary.
    expect(screen.getByTestId('event-detail-prev')).toBeDisabled();
    // Next advances to event 2.
    await user.click(screen.getByTestId('event-detail-next'));
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
        /Event 2 of 3/,
      );
    });
    // And advance once more.
    await user.click(screen.getByTestId('event-detail-next'));
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
        /Event 3 of 3/,
      );
    });
    // Next is disabled at the end.
    expect(screen.getByTestId('event-detail-next')).toBeDisabled();
  });
});

describe('Phase 3B · footer + resilience', () => {
  it('footer no longer advertises "Phase 2 · Overview & Catalog"', () => {
    installBffFetchMock({ index: emptyIndex });
    render(
      <AppShell initialIndex={emptyIndex}>
        <SessionRuntimePage />
      </AppShell>,
    );
    const footer = screen.getByTestId('app-shell-footer');
    expect(footer.textContent ?? '').not.toMatch(/Phase 2/);
    expect(footer.textContent ?? '').not.toMatch(/Overview & Catalog/);
    // And it still has a visible stable label.
    expect(footer).toHaveTextContent(/Read-only B5 surface/);
  });

  it('remains non-crashing when the session artifact is unloadable', async () => {
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
    // No structured overlay or extensions panel is rendered.
    expect(screen.queryByTestId('overlay-panel')).toBeNull();
    expect(screen.queryByTestId('ext-panel')).toBeNull();
    expect(screen.queryByTestId('event-detail')).toBeNull();
  });
});
