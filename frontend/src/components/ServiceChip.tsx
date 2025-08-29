'use client';

import React from 'react';

export default function ServiceChip({ name, status }: { name: string; status: string }) {
  const color = status === 'ok' ? 'bg-emerald-100 text-emerald-800' : status === 'degraded' ? 'bg-amber-100 text-amber-800' : status === 'skipped' ? 'bg-gray-100 text-gray-700' : 'bg-red-100 text-red-800';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ${color}`}>
      <span className="capitalize">{name}</span>
      <span>{status}</span>
    </span>
  );
}

