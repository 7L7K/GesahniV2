import { NextFetchEvent, NextRequest, NextResponse } from 'next/server'

export default function middleware(req: NextRequest, ev: NextFetchEvent) {
    const { pathname } = req.nextUrl

    // Bypass health endpoints and metrics completely - no auth, no redirects
    if (pathname.startsWith('/healthz/') || pathname === '/metrics') {
        return NextResponse.next()
    }
    return NextResponse.next()
}

export const config = {
    matcher: [
        // All app routes except static files, Next internals, and backend paths
        '/((?!v1/|healthz|metrics|shared_photos|album_art|_next/static|_next/image|favicon.ico|apple-touch-icon.png|capture/|.*\.(?:js|css|png|jpg|jpeg|gif|svg|ico|webp|woff|woff2|ttf)).*)',
        // Include Next.js API routes (not backend /v1)
        '/(api)(.*)'
    ],
}
