// frontend/next.config.js
const path = require('path');

/** @type {import('next').NextConfig} */
module.exports = {
  eslint: { ignoreDuringBuilds: true },
  webpack(config) {
    config.resolve.alias['@'] = path.resolve(__dirname, 'src');
    return config;
  },
  // Avoid Safari blowing up on new URL("") in Next dev hot reloader
  // by ensuring assetPrefix is a non-empty absolute URL in development.
  assetPrefix: (() => {
    const isDev = process.env.NODE_ENV !== 'production';
    // Prefer explicit config; fall back to site URL; last resort dev localhost
    const raw = process.env.NEXT_PUBLIC_ASSET_PREFIX
      || process.env.ASSET_PREFIX
      || (isDev ? (process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL || 'http://localhost:3000') : '');
    if (!raw) return undefined;
    try {
      const u = new URL(raw);
      // Normalize: strip trailing slash to match Next expectations
      return u.toString().replace(/\/$/, '');
    } catch {
      return undefined;
    }
  })(),
  // Ensure middleware executes on Vercel/Node runtime
  experimental: {
    middlewarePrefetch: 'flexible',
  },
  async rewrites() {
    return [
      {
        source: '/healthz/:path*',
        destination: 'http://localhost:8000/healthz/:path*',
      },
      {
        source: '/capture/:path*',
        destination: 'http://localhost:8000/capture/:path*',
      },
      {
        source: '/v1/:path*',
        destination: 'http://localhost:8000/v1/:path*',
      },
      {
        source: '/capture/start',
        destination: 'http://localhost:8000/capture/start',
      },
      {
        source: '/capture/save',
        destination: 'http://localhost:8000/capture/save',
      },
      // no WS rewrite—will connect directly
    ];
  },
  async headers() {
    return [
      {
        source: '/healthz/:path*',
        headers: [
          { key: 'x-debug-next', value: 'rewrite-to-8000' },
          { key: 'x-debug-source', value: '/healthz/:path*' },
        ],
      },
      // Mark responses that match rewrites to the backend
      {
        source: '/v1/:path*',
        headers: [
          { key: 'x-debug-next', value: 'rewrite-to-8000' },
          { key: 'x-debug-source', value: '/v1/:path*' },
        ],
      },
      {
        source: '/capture/:path*',
        headers: [
          { key: 'x-debug-next', value: 'rewrite-to-8000' },
          { key: 'x-debug-source', value: '/capture/:path*' },
        ],
      },
      // Flag Next static assets for quick visibility in devtools
      {
        source: '/_next/static/:path*',
        headers: [
          { key: 'x-debug-static', value: 'true' },
          { key: 'cache-control', value: 'public, max-age=0, must-revalidate' },
        ],
      },
      // Public assets
      {
        source: '/favicon.ico',
        headers: [
          { key: 'x-debug-public', value: 'true' },
        ],
      },
      {
        source: '/apple-touch-icon.png',
        headers: [
          { key: 'x-debug-public', value: 'true' },
        ],
      },
    ];
  },
};
