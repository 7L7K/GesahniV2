'use client'
import { SignIn } from '@clerk/nextjs'
import { useSearchParams } from 'next/navigation'

export default function SignInPage() {
    const params = useSearchParams();
    const next = (() => {
        const raw = (params.get('next') || '/').trim();
        try {
            if (!raw.startsWith('/') || raw.includes('://')) return '/';
            return raw.replace(/\/+/g, '/');
        } catch { return '/'; }
    })();
    const finishUrl = `/v1/auth/finish?next=${encodeURIComponent(next)}`;
    return (
        <div className="mx-auto max-w-md py-10">
            <SignIn routing="path" path="/sign-in" afterSignInUrl={finishUrl} afterSignUpUrl={finishUrl} />
        </div>
    )
}


