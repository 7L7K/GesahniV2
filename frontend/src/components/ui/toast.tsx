import { useEffect, useState } from 'react'

export function RateLimitToast() {
  const [visible, setVisible] = useState(false)
  const [seconds, setSeconds] = useState<number>(0)
  useEffect(() => {
    function onLimit(e: Event) {
      const det = (e as CustomEvent).detail as { retryAfter?: number }
      const s = Math.max(0, Number(det?.retryAfter || 0))
      setSeconds(s)
      setVisible(true)
    }
    window.addEventListener('rate-limit', onLimit as any)
    const id = setInterval(() => setSeconds((x) => (x > 0 ? x - 1 : 0)), 1000)
    return () => { window.removeEventListener('rate-limit', onLimit as any); clearInterval(id) }
  }, [])
  if (!visible) return null
  return (
    <div style={{ position: 'fixed', right: 16, bottom: 16, zIndex: 9999, background: '#111', color: '#fff', padding: '12px 14px', borderRadius: 12 }}>
      Too many requests, try again in {seconds}s
    </div>
  )
}

export function AuthMismatchToast() {
  const [visible, setVisible] = useState(false)
  const [message, setMessage] = useState<string>('')

  useEffect(() => {
    function onAuthMismatch(e: Event) {
      const det = (e as CustomEvent).detail as { message?: string }
      setMessage(det?.message || 'Auth mismatch—re-login.')
      setVisible(true)

      // Auto-hide after 5 seconds
      setTimeout(() => setVisible(false), 5000)
    }

    window.addEventListener('auth-mismatch', onAuthMismatch as any)
    return () => { window.removeEventListener('auth-mismatch', onAuthMismatch as any) }
  }, [])

  if (!visible) return null
  return (
    <div style={{ position: 'fixed', right: 16, bottom: 80, zIndex: 9999, background: '#dc2626', color: '#fff', padding: '12px 14px', borderRadius: 12, maxWidth: '300px' }}>
      {message}
    </div>
  )
}


