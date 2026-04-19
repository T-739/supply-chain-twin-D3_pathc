import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// Mock next/navigation at the module level. `usePathname` returns a
// controllable value via `__setMockPathname`; `redirect` throws
// so server components that call it surface as a test-time error
// (no Next.js runtime in vitest).
let mockPathname = '/overview';
vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  redirect: (target: string) => {
    throw new Error(`redirect(${target})`);
  },
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

// Exposed as a named export via test-setup side-effect — tests
// import it through this path.
export function __setMockPathname(p: string) {
  mockPathname = p;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  mockPathname = '/overview';
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      window.localStorage.clear();
    } catch {
      // ignore
    }
  }
});
