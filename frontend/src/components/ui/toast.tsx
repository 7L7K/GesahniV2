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


