import { NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export async function GET() {
    try {
        const { userId } = await auth()
        if (!userId) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
        }
        return NextResponse.json({ ok: true, userId })
    } catch {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
}
