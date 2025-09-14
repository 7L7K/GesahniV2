'use client';

import React from 'react';

export default function EmptyState() {
  return (
    <div className="flex items-center justify-center h-full py-12">
      <div className="max-w-md text-center border rounded-lg p-6 bg-background">
        <div className="text-lg mb-2">LLaMA’s napping; GPT-4o is on deck.</div>
        <div className="text-sm text-muted-foreground">Try: ‘Play dinner vibes.’</div>
      </div>
    </div>
  );
}
