'use client';

import type { ReactNode } from 'react';

import { BundleProvider } from './BundleContext';
import { BundleSelector } from './BundleSelector';
import { NavTabs } from './NavTabs';
import type { BundleIndexResponse } from '@/lib/types';

export interface AppShellProps {
  children: ReactNode;
  /** Test hooks — never used in production */
  initialIndex?: BundleIndexResponse | null;
  initialSelectedBundleId?: string | null;
}

/**
 * Global shell: header with brand + selector + nav tabs, main
 * outlet, honest footer. Every page in `app/` is rendered inside
 * this shell via the root layout.
 */
export function AppShell({
  children,
  initialIndex,
  initialSelectedBundleId,
}: AppShellProps) {
  return (
    <BundleProvider
      initialIndex={initialIndex}
      initialSelectedBundleId={initialSelectedBundleId}
    >
      <div className="app-shell">
        <a
          href="#app-main"
          className="app-shell__skip-link"
          data-testid="app-shell-skip-link"
        >
          Skip to main content
        </a>
        <header className="app-shell__header">
          <div className="app-shell__brand">
            <span className="app-shell__brand-line-1">
              Supply-Chain Digital Twin
            </span>
            <span className="app-shell__brand-line-2">
              Read-only thesis surface · B5
            </span>
          </div>
          <BundleSelector />
        </header>
        <NavTabs />
        <main
          id="app-main"
          className="app-shell__main"
          data-testid="app-main"
          tabIndex={-1}
        >
          {children}
        </main>
        <footer
          className="app-shell__footer"
          data-testid="app-shell-footer"
          role="contentinfo"
        >
          <span>
            Read-only B5 surface · supply-chain-twin-D3_pathc · artifact-driven
          </span>
        </footer>
      </div>
    </BundleProvider>
  );
}
