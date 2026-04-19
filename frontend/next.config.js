/**
 * Next.js config — B5 Phase 2.
 *
 * Notes:
 * - `B5_BFF_BASE_URL` defaults to the local FastAPI backend
 *   (`http://127.0.0.1:8001`) and is the single endpoint the
 *   frontend talks to. The `rewrites()` below proxies every
 *   `/api/bff/*` request to that base URL, so the browser never
 *   issues a cross-origin request and no CORS middleware is
 *   needed on the backend.
 * - No SSR data fetching at build time — pages fetch on the
 *   client so the dev experience remains simple (no BFF required
 *   for `next build`).
 */
const BFF_BASE_URL =
  process.env.B5_BFF_BASE_URL || 'http://127.0.0.1:8001';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/bff/:path*',
        destination: `${BFF_BASE_URL}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
