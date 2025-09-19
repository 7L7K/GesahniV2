import { NextFetchEvent, NextRequest, NextResponse } from 'next/server'

export default function middleware(req: NextRequest, ev: NextFetchEvent) {
    const { pathname } = req.nextUrl
    const timestamp = new Date().toISOString()

    // Very simple console logging to verify middleware is working
    console.log('='.repeat(80))
    console.log(`MIDDLEWARE TRIGGERED: ${timestamp}`)
    console.log(`PATH: ${pathname}`)
    console.log(`METHOD: ${req.method}`)
    console.log(`USER-AGENT: ${req.headers.get('user-agent')}`)
    console.log('='.repeat(80))

    // Log all page requests (excluding static assets and internal Next.js routes)
    if (!pathname.startsWith('/_next/') &&
        !pathname.startsWith('/assets/') &&
        !pathname.startsWith('/api/') &&
        !pathname.includes('.') &&
        pathname !== '/favicon.ico') {

        const userAgent = req.headers.get('user-agent') || 'unknown'
        const referer = req.headers.get('referer') || 'direct'
        const clientIP = req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || 'unknown'

        // Special logging for logout-related pages
        if (pathname.includes('logout') || pathname.includes('login')) {
            console.log('🚪'.repeat(10))
            console.log(`🚪 AUTH_PAGE_LOAD: ${timestamp}`)
            console.log(`🚪 Path: ${pathname}`)
            console.log(`🚪 User-Agent: ${userAgent.substring(0, 50)}...`)
            console.log(`🚪 Referer: ${referer}`)
            console.log(`🚪 IP: ${clientIP}`)
            console.log('🚪'.repeat(10))
        } else {
            console.log('📄'.repeat(10))
            console.log(`📄 PAGE_LOAD: ${timestamp}`)
            console.log(`📄 Path: ${pathname}`)
            console.log(`📄 User-Agent: ${userAgent.substring(0, 50)}...`)
            console.log(`📄 Referer: ${referer}`)
            console.log(`📄 IP: ${clientIP}`)
            console.log('📄'.repeat(10))
        }
    }

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
