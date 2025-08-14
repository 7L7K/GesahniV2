'use client'
import { SignUp } from '@clerk/nextjs'
import { useSearchParams } from 'next/navigation'

export default function SignUpPage() {
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
            <SignUp routing="path" path="/sign-up" afterSignInUrl={finishUrl} afterSignUpUrl={finishUrl} />
        </div>
    )
}


