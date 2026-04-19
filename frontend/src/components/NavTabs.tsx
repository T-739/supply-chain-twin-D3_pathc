'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { TABS } from '@/lib/constants';

/**
 * Top-level 5-tab navigation.
 *
 * In Phase 2 only `Overview` is real. The other tabs render a
 * neutral "not implemented yet" placeholder so the IA shape is
 * visible from day one without faking runtime semantics.
 */
export function NavTabs() {
  const pathname = usePathname() ?? '/';
  return (
    <nav className="nav-tabs" aria-label="Primary">
      <ul className="nav-tabs__list">
        {TABS.map((tab) => {
          const isActive =
            pathname === tab.href || pathname.startsWith(tab.href + '/');
          return (
            <li key={tab.href} className="nav-tabs__item">
              <Link
                href={tab.href}
                className={
                  'nav-tabs__link' +
                  (isActive ? ' nav-tabs__link--active' : '') +
                  (!tab.enabled ? ' nav-tabs__link--stub' : '')
                }
                aria-current={isActive ? 'page' : undefined}
                data-testid={`nav-tab-${tab.href.slice(1)}`}
              >
                {tab.label}
                {!tab.enabled && (
                  <span className="nav-tabs__badge" aria-label="placeholder">
                    placeholder
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
