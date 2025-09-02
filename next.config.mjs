/** @type {import('next').NextConfig} */
const nextConfig = {
    async rewrites() {
        // Enable a dev proxy when USE_DEV_PROXY is set to 'true' in the environment.
        // This lets the Next dev server proxy `/api/*` to the backend at 127.0.0.1:8000
        // so the frontend and backend appear same-origin during local development.
        if (process.env.USE_DEV_PROXY === 'true') {
            return [
                { source: '/api/:path*', destination: 'http://127.0.0.1:8000/:path*' },
            ];
        }
        return [];
    },
};

export default nextConfig;


