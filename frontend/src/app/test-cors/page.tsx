'use client';

import { useEffect, useState } from 'react';

interface TestResult {
    name: string;
    status: 'loading' | 'success' | 'error';
    message: string;
}

export default function CorsTestPage() {
    const [results, setResults] = useState<TestResult[]>([
        { name: 'Backend Health Check', status: 'loading', message: 'Testing...' },
        { name: 'Font Loading Test', status: 'loading', message: 'Testing...' },
        { name: 'API State Endpoint (Unauthorized Expected)', status: 'loading', message: 'Testing...' },
    ]);

    useEffect(() => {
        const runTests = async () => {
            const newResults = [...results];

            // Test 1: Backend Health Check
            try {
                const response = await fetch('http://127.0.0.1:8000/healthz/ready', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (response.ok) {
                    const data = await response.json();
                    newResults[0] = {
                        name: 'Backend Health Check',
                        status: 'success',
                        message: `Success: ${JSON.stringify(data)}`
                    };
                } else {
                    newResults[0] = {
                        name: 'Backend Health Check',
                        status: 'error',
                        message: `Error: ${response.status} ${response.statusText}`
                    };
                }
            } catch (error) {
                newResults[0] = {
                    name: 'Backend Health Check',
                    status: 'error',
                    message: `CORS Error: ${error instanceof Error ? error.message : 'Unknown error'}`
                };
            }

            // Test 2: Font Loading Test
            try {
                const response = await fetch('http://localhost:3000/_next/static/media/569ce4b8f30dc480-s.p.woff2', {
                    method: 'GET'
                });

                if (response.ok) {
                    newResults[1] = {
                        name: 'Font Loading Test',
                        status: 'success',
                        message: `Font loaded successfully (${response.headers.get('content-length')} bytes)`
                    };
                } else {
                    newResults[1] = {
                        name: 'Font Loading Test',
                        status: 'error',
                        message: `Font Error: ${response.status} ${response.statusText}`
                    };
                }
            } catch (error) {
                newResults[1] = {
                    name: 'Font Loading Test',
                    status: 'error',
                    message: `Font CORS Error: ${error instanceof Error ? error.message : 'Unknown error'}`
                };
            }

            // Test 3: API State Endpoint
            try {
                const response = await fetch('http://127.0.0.1:8000/v1/state', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (response.status === 401) {
                    newResults[2] = {
                        name: 'API State Endpoint (Unauthorized Expected)',
                        status: 'success',
                        message: 'Expected 401 Unauthorized (authentication required)'
                    };
                } else {
                    newResults[2] = {
                        name: 'API State Endpoint (Unauthorized Expected)',
                        status: 'error',
                        message: `Unexpected: ${response.status} ${response.statusText}`
                    };
                }
            } catch (error) {
                newResults[2] = {
                    name: 'API State Endpoint (Unauthorized Expected)',
                    status: 'error',
                    message: `CORS Error: ${error instanceof Error ? error.message : 'Unknown error'}`
                };
            }

            setResults(newResults);
        };

        runTests();
    }, []);

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'success': return '✓';
            case 'error': return '✗';
            default: return '⏳';
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'success': return 'text-green-600';
            case 'error': return 'text-red-600';
            default: return 'text-orange-600';
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 py-8">
            <div className="max-w-4xl mx-auto px-4">
                <h1 className="text-3xl font-bold text-gray-900 mb-8">CORS Test Results</h1>

                <div className="space-y-6">
                    {results.map((result, index) => (
                        <div key={index} className="bg-white rounded-lg shadow-md p-6">
                            <h2 className="text-xl font-semibold text-gray-800 mb-3">{result.name}</h2>
                            <div className={`flex items-center space-x-2 ${getStatusColor(result.status)}`}>
                                <span className="text-lg font-bold">{getStatusIcon(result.status)}</span>
                                <span className="text-sm">{result.message}</span>
                            </div>
                        </div>
                    ))}
                </div>

                <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <h3 className="text-lg font-semibold text-blue-900 mb-2">Test Information</h3>
                    <p className="text-blue-800 text-sm">
                        This page tests CORS functionality between the frontend (localhost:3000) and backend (127.0.0.1:8000).
                        The font loading test verifies that static assets are served with proper CORS headers.
                    </p>
                </div>
            </div>
        </div>
    );
}
