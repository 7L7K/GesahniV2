'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
export default function SignInPage() {
    const router = useRouter();
    useEffect(() => {
        // Always redirect to login without next parameter
        router.replace('/login');
    }, [router]);
    return (
        <div className="mx-auto max-w-md py-10">
            <p className="text-sm text-muted-foreground">Redirecting to login…</p>
        </div>
    )
}
