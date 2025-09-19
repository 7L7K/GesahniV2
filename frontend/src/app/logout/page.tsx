'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { clearTokens, apiFetch } from '@/lib/api'
import { getAuthOrchestrator } from '@/services/authOrchestrator'
import { whoamiCache } from '@/lib/whoamiCache'
import { whoamiDedupe } from '@/lib/whoamiDedupe'

export default function LogoutPage() {
    const router = useRouter()

    useEffect(() => {
        const performLogout = async () => {
            console.log('🚪 LOGOUT: Starting logout process...')
            console.log('🚪 LOGOUT: Current cookies before logout:', document.cookie)

            const orchestrator = getAuthOrchestrator()
            orchestrator.setLogoutInProgress(true)

            try {
                // 1) Clear whoami cache *before* we call the API
                console.log('🚪 LOGOUT: Clearing whoami cache...')
                whoamiCache.clear()

                // 2) Disable dedupe for next whoami call
                console.log('🚪 LOGOUT: Disabling dedupe for next whoami call...')
                whoamiDedupe.disableOnce()

                try {
                    console.log('🚪 LOGOUT: Making API call to /v1/auth/logout')
                    const response = await apiFetch('/v1/auth/logout', {
                        method: 'POST',
                        auth: true,
                        cache: 'no-store',
                        headers: { 'X-Auth-Orchestrator': 'legitimate' }
                    })
                    console.log('🚪 LOGOUT: API response received:', {
                        status: response.status,
                        statusText: response.statusText,
                        ok: response.ok
                    })

                    if (!response.ok && response.status !== 204) {
                        console.error('🚪 LOGOUT: API call failed with status:', response.status)
                    } else {
                        console.log('🚪 LOGOUT: API call successful')

                        // Broadcast logout to all tabs for instant fan-out
                        console.log('🚪 LOGOUT: Broadcasting logout to all tabs...')
                        try {
                            const bc = new BroadcastChannel('auth');
                            bc.postMessage({ type: 'logout', timestamp: Date.now() });
                            bc.close();
                            console.log('🚪 LOGOUT: Logout broadcasted successfully')
                        } catch (error) {
                            console.warn('🚪 LOGOUT: Failed to broadcast logout:', error)
                        }
                    }
                } catch (error) {
                    console.error('🚪 LOGOUT: API call exception:', error)
                }

                console.log('🚪 LOGOUT: Clearing local tokens...')
                try {
                    clearTokens()
                    console.log('🚪 LOGOUT: Local tokens cleared successfully')
                } catch (error) {
                    console.error('🚪 LOGOUT: Failed to clear local tokens:', error)
                }

                // 4) Force a fresh whoami read (no cache, no dedupe)
                try {
                    orchestrator.markExplicitStateChange()
                    await orchestrator.refreshAuth({ force: true, noDedupe: true, noCache: true })
                } catch (error) {
                    console.warn('🚪 LOGOUT: Forced auth refresh after clearTokens failed:', error)
                }

                console.log('🚪 LOGOUT: Cookies after token clearing:', document.cookie)

                console.log('🚪 LOGOUT: Navigating to login page...')
                try {
                    router.replace('/login?logout=true')
                    console.log('🚪 LOGOUT: Navigation initiated')
                } catch (error) {
                    console.error('🚪 LOGOUT: Navigation failed:', error)
                }

                console.log('🚪 LOGOUT: Logout process completed')
            } finally {
                orchestrator.setLogoutInProgress(false)
            }
        };

        performLogout();
    }, [router])
    return (
        <main className="mx-auto max-w-md px-4 py-10">
            <p className="text-sm text-muted-foreground">Signing you out…</p>
        </main>
    )
}
