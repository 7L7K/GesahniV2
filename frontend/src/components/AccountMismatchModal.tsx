'use client';

import React from 'react';
import { connectGoogle } from '@/lib/api/integrations';
import { toast } from '@/lib/toast';

export default function AccountMismatchModal({ open, onClose, onReconnect, onDisconnectOther } : { open: boolean; onClose: ()=>void; onReconnect?: ()=>void; onDisconnectOther?: ()=>void }){
  if (!open) return null;
  const handleReconnect = async ()=>{
    try{ const res = await connectGoogle();
      if (res?.authorize_url) window.location.href = res.authorize_url;
      onReconnect?.();
    }catch(e:any){ toast.error('Failed to start reconnect'); }
  }
  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="bg-white p-6 rounded shadow-lg z-10 w-full max-w-md">
        <h3 className="text-lg font-semibold">Account Mismatch</h3>
        <p className="mt-2 text-sm">It looks like Gmail and Calendar are connected to different Google accounts. Choose how to proceed.</p>
        <div className="mt-4 flex gap-2">
          <button className="px-3 py-2 bg-blue-600 text-white rounded" onClick={handleReconnect}>Reconnect with existing account</button>
          <button className="px-3 py-2 border rounded" onClick={()=>{ onDisconnectOther?.(); toast.info('Please disconnect the other account first.'); }}>Disconnect other account</button>
          <button className="px-3 py-2 text-sm" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

