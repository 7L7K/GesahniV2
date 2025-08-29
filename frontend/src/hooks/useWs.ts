'use client';

import { useEffect, useState } from 'react';
import { wsHub } from '@/services/wsHub';

export function useWsOpen(name: 'music' | 'care', intervalMs: number = 3000) {
  const [open, setOpen] = useState<boolean>(() => wsHub.getConnectionStatus(name).isOpen);
  useEffect(() => {
    let mounted = true;
    const check = () => { if (!mounted) return; setOpen(wsHub.getConnectionStatus(name).isOpen); };
    const id = window.setInterval(check, intervalMs);
    check();
    return () => { mounted = false; window.clearInterval(id); };
  }, [name, intervalMs]);
  return open;
}

