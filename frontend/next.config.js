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
      || (isDev ? (process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL || 'http://127.0.0.1:3000') : '');
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
  // Removed rewrites to eliminate double-layer API calls and cookie site issues
  // All API calls now go directly to http://127.0.0.1:8000 via NEXT_PUBLIC_API_ORIGIN
  async headers() {
    return [
      // Global CSP header for all pages
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: "default-src 'self'; connect-src 'self' http://127.0.0.1:8000 ws://127.0.0.1:8000 http://localhost:8000 ws://localhost:8000; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'; upgrade-insecure-requests"
          },
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
