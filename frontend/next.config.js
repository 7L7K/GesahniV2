// frontend/next.config.js
const path = require('path');

/** @type {import('next').NextConfig} */
module.exports = {
  eslint: { ignoreDuringBuilds: true },
  webpack(config) {
    config.resolve.alias['@'] = path.resolve(__dirname, 'src');
    return config;
  },
  async rewrites() {
    return [
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
};
