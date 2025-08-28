'use client'
import { useEffect } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { sanitizeNextPath } from '@/lib/utils'

export default function SignInPage() {
    const params = useSearchParams();
    const router = useRouter();
    useEffect(() => {
        const next = sanitizeNextPath(params.get('next'), '/');
        router.replace(`/login?next=${encodeURIComponent(next)}`)
    }, [params, router]);
    return (
        <div className="mx-auto max-w-md py-10">
            <p className="text-sm text-muted-foreground">Redirecting to login…</p>
        </div>
    )
}
