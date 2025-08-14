'use client'
import { SignIn } from '@clerk/nextjs'

export default function SignInPage() {
    return (
        <div className="mx-auto max-w-md py-10">
            <SignIn routing="path" path="/sign-in" />
        </div>
    )
}


