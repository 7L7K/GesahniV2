'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

export default function DebugPage() {
    const [results, setResults] = useState<any>({});

    useEffect(() => {
        const testHealth = async () => {
            const results: any = {};

            // Show environment variables
            results.env = {
                NEXT_PUBLIC_API_ORIGIN: process.env.NEXT_PUBLIC_API_ORIGIN,
                NODE_ENV: process.env.NODE_ENV,
            };

            try {
                console.log('Testing health endpoint...');
                const res = await apiFetch('/healthz/ready', {
                    auth: false,
                    cache: 'no-store'
                });
                results.health = {
                    status: res.status,
                    ok: res.ok,
                    url: res.url,
                    headers: Object.fromEntries(res.headers.entries())
                };
                if (res.ok) {
                    const body = await res.json();
                    results.health.body = body;
                }
            } catch (error) {
                results.health = { error: error instanceof Error ? error.message : String(error) };
            }

            setResults(results);
        };

        testHealth();
    }, []);

    return (
        <div className="p-8">
            <h1 className="text-2xl font-bold mb-4">API Debug</h1>
            <pre className="bg-gray-100 p-4 rounded overflow-auto">
                {JSON.stringify(results, null, 2)}
            </pre>
        </div>
    );
}
