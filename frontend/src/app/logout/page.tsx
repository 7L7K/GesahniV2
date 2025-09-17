'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { clearTokens, apiFetch } from '@/lib/api'
export default function LogoutPage() {
    const router = useRouter()
    useEffect(() => {
        const performLogout = async () => {
            try {
                // Start all logout operations concurrently
                await apiFetch('/v1/auth/logout', { method: 'POST' }).catch(() => { })
            } catch (error) {
                console.warn('Logout API call failed:', error);
            }

            // Clear local tokens immediately
            try { clearTokens() } catch { /* ignore */ }

            // Navigate immediately
            router.replace('/login?logout=true')
        };

        performLogout();
    }, [router])
    return (
        <main className="mx-auto max-w-md px-4 py-10">
            <p className="text-sm text-muted-foreground">Signing you out…</p>
        </main>
    )
}
