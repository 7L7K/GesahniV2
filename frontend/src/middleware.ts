import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextFetchEvent, NextRequest, NextResponse } from 'next/server'
import { buildRedirectUrl, sanitizeNextPath } from '@/lib/urls'

const isPublicRoute = createRouteMatcher([
    '/',
    '/docs(.*)',
    '/login',
    '/debug',
])

const baseClerkMiddleware = clerkMiddleware(async (auth, req: NextRequest) => {
    const { userId } = await auth()
    // Only guard Next's own API; allow /v1/* to flow to FastAPI via rewrites
    const isApi = req.nextUrl.pathname.startsWith('/api')
    if (isApi && !userId) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    if (!isPublicRoute(req) && !userId) {
        const url = buildRedirectUrl(req, '/', {
            next: req.nextUrl.pathname + req.nextUrl.search
        })
        return NextResponse.redirect(url)
    }
    // If Clerk finished login on our domain, bounce through server finish route
    try {
        const pathname = req.nextUrl.pathname
        if (userId && (pathname === '/sign-in' || pathname === '/sign-up')) {
            const next = sanitizeNextPath(req.nextUrl.searchParams.get('next'), '/')
            const url = buildRedirectUrl(req, '/v1/auth/finish', { next })
            return NextResponse.redirect(url)
        }
    } catch { /* ignore */ }
    return NextResponse.next()
})

export default function middleware(req: NextRequest, ev: NextFetchEvent) {
    const { pathname } = req.nextUrl

    // Bypass health endpoints and metrics completely - no auth, no redirects
    if (pathname.startsWith('/healthz/') || pathname === '/metrics') {
        return NextResponse.next()
    }

    // Temporarily disable Clerk middleware during Google OAuth stabilization so only Google OAuth is active.
    const hasClerk = false
    if (hasClerk) {
        return baseClerkMiddleware(req, ev)
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


