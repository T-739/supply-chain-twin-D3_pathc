/**
 * Single data adapter between the frontend and the B5 BFF.
 *
 * The frontend MUST NOT read bundle files directly. Every call
 * that needs bundle data goes through this module, and this
 * module only talks to the BFF over HTTP.
 *
 * Default transport: same-origin `/api/bff/*` which is proxied
 * to the BFF in `next.config.js`. Tests replace this module's
 * fetch by stubbing `globalThis.fetch` — no other seam is
 * provided or supported.
 */

import type {
  BundleDetailResponse,
  BundleIndexResponse,
  SessionArtifactResponse,
} from './types';

export const BFF_PREFIX = '/api/bff';

export class BffError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    message: string,
  ) {
    super(message);
    this.name = 'BffError';
  }
}

async function bffGet<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BFF_PREFIX}${path}`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new BffError(
      res.status,
      path,
      `BFF GET ${path} failed: ${res.status} ${res.statusText}${
        body ? ` — ${body}` : ''
      }`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchBundleIndex(): Promise<BundleIndexResponse> {
  return bffGet<BundleIndexResponse>('/bundles');
}

export async function fetchBundleDetail(
  bundleId: string,
): Promise<BundleDetailResponse> {
  if (!bundleId) {
    throw new BffError(0, '/bundles/', 'bundleId is required');
  }
  return bffGet<BundleDetailResponse>(
    `/bundles/${encodeURIComponent(bundleId)}`,
  );
}

export async function fetchSessionArtifact(
  bundleId: string,
  variantTag: string,
): Promise<SessionArtifactResponse> {
  if (!bundleId) {
    throw new BffError(0, '/bundles/', 'bundleId is required');
  }
  if (!variantTag) {
    throw new BffError(0, '/sessions/', 'variantTag is required');
  }
  return bffGet<SessionArtifactResponse>(
    `/bundles/${encodeURIComponent(bundleId)}/sessions/${encodeURIComponent(
      variantTag,
    )}`,
  );
}

export async function fetchHealth(): Promise<{ status: string }> {
  return bffGet<{ status: string }>('/healthz');
}
