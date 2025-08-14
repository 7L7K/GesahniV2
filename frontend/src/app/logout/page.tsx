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
            try { await apiFetch('/v1/auth/logout', { method: 'POST' }) } catch { /* ignore */ }
            try { await signOut?.() } catch { /* ignore */ }
            try { clearTokens() } catch { /* ignore */ }
            try { document.cookie = 'auth_hint=0; path=/; max-age=300' } catch { /* ignore */ }
            router.replace('/sign-in')
        })()
    }, [router, signOut])
    return (
        <main className="mx-auto max-w-md px-4 py-10">
            <p className="text-sm text-muted-foreground">Signing you out…</p>
        </main>
    )
}


