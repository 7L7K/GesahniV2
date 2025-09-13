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
  // Bundle optimization
  // optimizeFonts and swcMinify are deprecated in Next.js 15+
  // These are now enabled by default
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? {
      exclude: ['error', 'warn']
    } : false,
  },
  // Reduce development noise
  onDemandEntries: {
    // period (in ms) where the server will keep pages in the buffer
    maxInactiveAge: 25 * 1000,
    // number of pages that should be kept simultaneously without being disposed
    pagesBufferLength: 2,
  },
  // Development proxy: keep API same-origin to avoid Safari third-party cookie issues
  // When NEXT_PUBLIC_USE_DEV_PROXY=true, frontend will call relative paths and these
  // rewrites will proxy them to the backend at http://localhost:8000
  async rewrites() {
    const flag = String(process.env.NEXT_PUBLIC_USE_DEV_PROXY || process.env.USE_DEV_PROXY || 'false').toLowerCase();
    const useProxy = ['true', '1', 'yes', 'on'].includes(flag);
    if (!useProxy) return [];
    const backend = process.env.NEXT_PUBLIC_API_ORIGIN || 'http://localhost:8000';
    // Normalize trailing slash
    const target = backend.replace(/\/$/, '');
    return [
      { source: '/v1/:path*', destination: `${target}/v1/:path*` },
      { source: '/healthz/:path*', destination: `${target}/healthz/:path*` },
      { source: '/health/:path*', destination: `${target}/health/:path*` },
      { source: '/metrics', destination: `${target}/metrics` },
      { source: '/debug/:path*', destination: `${target}/debug/:path*` },
      // Optional: static mounts proxied for convenience
      { source: '/shared_photos/:path*', destination: `${target}/shared_photos/:path*` },
      { source: '/album_art/:path*', destination: `${target}/album_art/:path*` },
    ];
  },
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
