import { vi } from 'vitest';

import type {
  BundleDetailResponse,
  BundleIndexResponse,
  SessionArtifactResponse,
} from '@/lib/types';

/**
 * Install a deterministic fetch mock that serves the BFF surface
 * we care about. Responses are JSON structures passed in by the
 * caller; anything else returns a 500 so tests fail loudly.
 */
export function installBffFetchMock(options: {
  index?: BundleIndexResponse | null;
  detailsByBundleId?: Record<string, BundleDetailResponse>;
  sessionArtifactsByKey?: Record<string, SessionArtifactResponse>;
}) {
  const {
    index,
    detailsByBundleId = {},
    sessionArtifactsByKey = {},
  } = options;

  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.endsWith('/api/bff/bundles') || url.endsWith('/api/bff/bundles/')) {
      if (index === null) {
        return new Response('internal error', {
          status: 500,
          statusText: 'Internal Server Error',
        });
      }
      return new Response(JSON.stringify(index), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    // Longest path first — session-artifact route must match
    // before the shallow detail route.
    const artifactMatch = url.match(
      /\/api\/bff\/bundles\/([^/?#]+)\/sessions\/([^/?#]+)/,
    );
    if (artifactMatch) {
      const bid = decodeURIComponent(artifactMatch[1]);
      const tag = decodeURIComponent(artifactMatch[2]);
      const key = `${bid}::${tag}`;
      const payload = sessionArtifactsByKey[key];
      if (!payload) {
        return new Response(JSON.stringify({ detail: 'not found' }), {
          status: 404,
          statusText: 'Not Found',
        });
      }
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const detailMatch = url.match(/\/api\/bff\/bundles\/([^/?#]+)/);
    if (detailMatch) {
      const id = decodeURIComponent(detailMatch[1]);
      const detail = detailsByBundleId[id];
      if (!detail) {
        return new Response(JSON.stringify({ detail: 'not found' }), {
          status: 404,
          statusText: 'Not Found',
        });
      }
      return new Response(JSON.stringify(detail), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response('unexpected URL: ' + url, { status: 500 });
  });

  vi.stubGlobal('fetch', mock);
  return mock;
}

export function artifactKey(bundleId: string, variantTag: string): string {
  return `${bundleId}::${variantTag}`;
}
