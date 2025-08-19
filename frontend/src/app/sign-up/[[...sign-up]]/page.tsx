'use client'
import { SignUp } from '@clerk/nextjs'
import { useSearchParams } from 'next/navigation'
import { buildAuthUrl } from '@/lib/urls'
import { sanitizeNextPath } from '@/lib/utils'

export default function SignUpPage() {
    const params = useSearchParams();
    const next = sanitizeNextPath(params.get('next'), '/');
    const finishUrl = buildAuthUrl('/v1/auth/finish', next);
    return (
        <div className="mx-auto max-w-md py-10">
            <SignUp routing="path" path="/sign-up" afterSignInUrl={finishUrl} afterSignUpUrl={finishUrl} />
        </div>
    )
}


