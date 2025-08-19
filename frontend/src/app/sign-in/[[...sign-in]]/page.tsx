'use client'
import { SignIn } from '@clerk/nextjs'
import { useSearchParams } from 'next/navigation'
import { buildAuthUrl } from '@/lib/urls'
import { sanitizeNextPath } from '@/lib/utils'

export default function SignInPage() {
    const params = useSearchParams();
    const next = sanitizeNextPath(params.get('next'), '/');
    const finishUrl = buildAuthUrl('/v1/auth/finish', next);
    return (
        <div className="mx-auto max-w-md py-10">
            <SignIn routing="path" path="/sign-in" afterSignInUrl={finishUrl} afterSignUpUrl={finishUrl} />
        </div>
    )
}


