'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { clearTokens, apiFetch } from '@/lib/api'
export default function LogoutPage() {
    const router = useRouter()

    // Safely get Clerk signOut function only when Clerk is enabled
    const getSignOut = () => {
        const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
        if (!clerkEnabled) {
            return () => Promise.resolve();
        }
        try {
            const { useClerk } = require('@clerk/nextjs');
            const { signOut } = useClerk();
            return signOut;
        } catch (error) {
            console.warn('Clerk not available:', error);
            return () => Promise.resolve();
        }
    };

    const signOut = getSignOut();
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

            // Clear local tokens immediately
            try { clearTokens() } catch { /* ignore */ }

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


