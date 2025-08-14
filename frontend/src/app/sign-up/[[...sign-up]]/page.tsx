'use client'
import { SignUp } from '@clerk/nextjs'

export default function SignUpPage() {
    return (
        <div className="mx-auto max-w-md py-10">
            <SignUp routing="path" path="/sign-up" />
        </div>
    )
}


