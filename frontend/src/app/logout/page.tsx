'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { clearTokens, apiFetch } from '@/lib/api'
import { useClerk } from '@clerk/nextjs'

export default function LogoutPage() {
    const router = useRouter()
    const { signOut } = useClerk()
    useEffect(() => {
        (async () => {
            // Start all logout operations concurrently
            const logoutPromises = [
                // Backend logout
                apiFetch('/v1/auth/logout', { method: 'POST' }).catch(() => { }),
                // Clerk signOut (non-blocking)
                signOut?.().catch(() => { }),
            ]

            // Wait for backend logout to complete, but don't wait for Clerk
            await logoutPromises[0]

            // Clear local tokens and cookies immediately
            try { clearTokens() } catch { /* ignore */ }
            try { document.cookie = 'auth_hint=0; path=/; max-age=300' } catch { /* ignore */ }

            // Navigate immediately
            router.replace('/sign-in')

            // Let Clerk signOut complete in background
            logoutPromises[1].catch(() => { })
        })()
    }, [router, signOut])
    return (
        <main className="mx-auto max-w-md px-4 py-10">
            <p className="text-sm text-muted-foreground">Signing you out…</p>
        </main>
    )
}


