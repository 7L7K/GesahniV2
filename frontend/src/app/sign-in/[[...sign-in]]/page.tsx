'use client'
import { useEffect } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { sanitizeNextPath } from '@/lib/utils'

export default function SignInPage() {
    const params = useSearchParams();
    const router = useRouter();
    useEffect(() => {
        const next = sanitizeNextPath(params?.get('next') || null, '/');
        // Prevent redirect loops by not redirecting to login if we're already on a login-related page
        if (!next.includes('/login') && !next.includes('/sign-in') && !next.includes('/sign-up')) {
            router.replace(`/login?next=${encodeURIComponent(next)}`);
        } else {
            router.replace('/login');
        }
    }, [params, router]);
    return (
        <div className="mx-auto max-w-md py-10">
            <p className="text-sm text-muted-foreground">Redirecting to login…</p>
        </div>
    )
}
