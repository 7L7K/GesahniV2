// frontend/next.config.js
const path = require('path');

/** @type {import('next').NextConfig} */
module.exports = {
  eslint: { ignoreDuringBuilds: true },
  webpack(config, { isServer }) {
    // Path alias for src/
    config.resolve.alias['@'] = path.resolve(__dirname, 'src');

    // Ensure server runtime looks for chunks in server/chunks
    // Fixes runtime requiring './<id>.js' instead of './chunks/<id>.js'
    if (isServer) {
      config.output = {
        ...config.output,
        chunkFilename: 'chunks/[id].js',
      };
    }

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
  // Configure base URL to prevent localhost proxy issues
  basePath: '',
  trailingSlash: false,
  // Ensure middleware executes on Vercel/Node runtime
  experimental: {
    middlewarePrefetch: 'flexible',
  },
  // Reduce development noise
  onDemandEntries: {
    // period (in ms) where the server will keep pages in the buffer
    maxInactiveAge: 25 * 1000,
    // number of pages that should be kept simultaneously without being disposed
    pagesBufferLength: 2,
  },
  // Removed rewrites to eliminate double-layer API calls and cookie site issues
  // All API calls now go directly to http://localhost:8000 via NEXT_PUBLIC_API_ORIGIN
  async headers() {
    return [
      // Flag Next static assets for quick visibility in devtools
      {
        source: '/_next/static/:path*',
        headers: [
          { key: 'x-debug-static', value: 'true' },
          { key: 'cache-control', value: 'public, max-age=0, must-revalidate' },
          // Add CORS headers for static assets to fix font loading issues
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Content-Type' },
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
  // Note: Server configuration is handled via command line arguments
  // -H :: binds to all interfaces
};
