import { NextFetchEvent, NextRequest, NextResponse } from 'next/server'
import { sanitizeNextPath } from '@/lib/urls'

export default function middleware(req: NextRequest, ev: NextFetchEvent) {
    const { pathname } = req.nextUrl

    // Bypass health endpoints and metrics completely - no auth, no redirects
    if (pathname.startsWith('/healthz/') || pathname === '/metrics') {
        return NextResponse.next()
    }

    // Exclude auth-related paths from auth guard
    if (pathname.startsWith('/login') ||
        pathname.startsWith('/sign-in') ||
        pathname.startsWith('/sign-up') ||
        pathname.startsWith('/api/') ||
        pathname.startsWith('/_next/') ||
        pathname.startsWith('/assets/') ||
        pathname === '/favicon.ico') {
        return NextResponse.next()
    }

    return NextResponse.next()
}

export const config = {
    matcher: [
        // Skip Next.js internals completely
        '/((?!__nextjs_|_next/static|_next/webpack-hmr|_next/development|_next/image|v1/|healthz|metrics|shared_photos|album_art|favicon.ico|apple-touch-icon.png|capture/|.*\.(?:js|css|png|jpg|jpeg|gif|svg|ico|webp|woff|woff2|ttf)).*)',
        // Include Next.js API routes (not backend /v1)
        '/(api)(.*)'
    ],
}
