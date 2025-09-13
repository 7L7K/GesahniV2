'use client';

import Link from 'next/link';

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-2">Dashboard</h1>
      <p className="text-sm text-gray-600 mb-6">
        You are signed in. This is a minimal placeholder dashboard.
      </p>
      <div className="space-x-3">
        <Link href="/" className="underline text-blue-600">Home</Link>
        <Link href="/chat" className="underline text-blue-600">Chat</Link>
        <Link href="/settings" className="underline text-blue-600">Settings</Link>
      </div>
    </main>
  );
}
