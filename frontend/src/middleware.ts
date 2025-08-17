import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextFetchEvent, NextRequest, NextResponse } from 'next/server'

function sanitizeNextPath(raw: string | null | undefined, fallback: string = '/') {
    const input = (raw || '').trim()
    if (!input) return fallback
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(input)) return fallback
    if (!input.startsWith('/')) return fallback
    return input.replace(/\/+/, '/')
}

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
        const url = req.nextUrl.clone()
        url.pathname = '/'
        url.searchParams.set('next', req.nextUrl.pathname + req.nextUrl.search)
        return NextResponse.redirect(url)
    }
    // If Clerk finished login on our domain, bounce through server finish route
    try {
        const pathname = req.nextUrl.pathname
        if (userId && (pathname === '/sign-in' || pathname === '/sign-up')) {
            const next = sanitizeNextPath(req.nextUrl.searchParams.get('next'), '/')
            const url = req.nextUrl.clone()
            url.pathname = '/v1/auth/finish'
            url.searchParams.set('next', next)
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

    const hasClerk = Boolean(process.env.CLERK_SECRET_KEY || process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)
    const { searchParams } = req.nextUrl
    // Preserve legacy token capture for backend cookie auth
    if (pathname === '/login' && (searchParams.has('access_token') || searchParams.has('refresh_token'))) {
        const access = searchParams.get('access_token') || ''
        const refresh = searchParams.get('refresh_token') || ''
        const next = sanitizeNextPath(searchParams.get('next'), '/')
        const res = NextResponse.redirect(new URL(next, req.url))
        if (access) {
            res.cookies.set('access_token', access, {
                httpOnly: true,
                sameSite: (process.env.COOKIE_SAMESITE || 'lax').toLowerCase() as any,
                secure: (process.env.NODE_ENV === 'production') || (process.env.COOKIE_SECURE || '1').toLowerCase() === '1',
                path: '/',
                maxAge: Number(process.env.NEXT_PUBLIC_JWT_EXPIRE_MINUTES || process.env.JWT_EXPIRE_MINUTES || 30) * 60,
            })
        }
        if (refresh) {
            const refreshMinutes = Number(process.env.NEXT_PUBLIC_JWT_REFRESH_EXPIRE_MINUTES || process.env.JWT_REFRESH_EXPIRE_MINUTES || 1440)
            res.cookies.set('refresh_token', refresh, {
                httpOnly: true,
                sameSite: (process.env.COOKIE_SAMESITE || 'lax').toLowerCase() as any,
                secure: (process.env.NODE_ENV === 'production') || (process.env.COOKIE_SECURE || '1').toLowerCase() === '1',
                path: '/',
                maxAge: refreshMinutes * 60,
            })
        }
        res.cookies.set('auth_hint', '1', { path: '/', maxAge: 14 * 24 * 60 * 60 })
        return res
    }
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


