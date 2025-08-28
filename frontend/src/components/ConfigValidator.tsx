'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

interface ConfigIssue {
    type: 'error' | 'warning' | 'info';
    message: string;
    suggestion?: string;
}

export function ConfigValidator() {
    const [issues, setIssues] = useState<ConfigIssue[]>([]);
    const [isChecking, setIsChecking] = useState(true);

    useEffect(() => {
        const checkConfiguration = () => {
            const newIssues: ConfigIssue[] = [];

            // Clerk removed: cookie/header auth only

            // Check API configuration
            const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN;
            if (!apiOrigin) {
                newIssues.push({
                    type: 'error',
                    message: 'API origin is not configured',
                    suggestion: 'Add NEXT_PUBLIC_API_ORIGIN to .env.local (e.g., http://localhost:8000)'
                });
            }

            // Check site URL configuration
            const siteUrl = process.env.NEXT_PUBLIC_SITE_URL;
            if (!siteUrl) {
                newIssues.push({
                    type: 'warning',
                    message: 'Site URL is not configured',
                    suggestion: 'Add NEXT_PUBLIC_SITE_URL to .env.local (e.g., http://localhost:3000)'
                });
            }

            // Check authentication mode
            const headerAuthMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE;
            if (headerAuthMode === undefined) {
                newIssues.push({
                    type: 'info',
                    message: 'Authentication mode not explicitly set',
                    suggestion: 'Set NEXT_PUBLIC_HEADER_AUTH_MODE=1 for header-based auth or NEXT_PUBLIC_HEADER_AUTH_MODE=0 for cookie-based auth'
                });
            }

            setIssues(newIssues);
            setIsChecking(false);
        };

        checkConfiguration();
    }, []);

    if (isChecking) {
        return (
            <div className="fixed top-4 right-4 bg-blue-50 border border-blue-200 rounded-lg p-4 max-w-md">
                <div className="flex items-center space-x-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                    <span className="text-sm text-blue-800">Checking configuration...</span>
                </div>
            </div>
        );
    }

    if (issues.length === 0) {
        return null;
    }

    const errors = issues.filter(issue => issue.type === 'error');
    const warnings = issues.filter(issue => issue.type === 'warning');
    const infos = issues.filter(issue => issue.type === 'info');

    return (
        <div className="fixed top-4 right-4 bg-white border border-gray-200 rounded-lg p-4 max-w-md shadow-lg z-50">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-900">Configuration Status</h3>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIssues([])}
                    className="text-gray-400 hover:text-gray-600"
                >
                    ×
                </Button>
            </div>

            <div className="space-y-2">
                {errors.map((issue, index) => (
                    <div key={index} className="bg-red-50 border border-red-200 rounded p-2">
                        <div className="text-sm font-medium text-red-800">⚠️ {issue.message}</div>
                        {issue.suggestion && (
                            <div className="text-xs text-red-600 mt-1">{issue.suggestion}</div>
                        )}
                    </div>
                ))}

                {warnings.map((issue, index) => (
                    <div key={index} className="bg-yellow-50 border border-yellow-200 rounded p-2">
                        <div className="text-sm font-medium text-yellow-800">⚠️ {issue.message}</div>
                        {issue.suggestion && (
                            <div className="text-xs text-yellow-600 mt-1">{issue.suggestion}</div>
                        )}
                    </div>
                ))}

                {infos.map((issue, index) => (
                    <div key={index} className="bg-blue-50 border border-blue-200 rounded p-2">
                        <div className="text-sm font-medium text-blue-800">ℹ️ {issue.message}</div>
                        {issue.suggestion && (
                            <div className="text-xs text-blue-600 mt-1">{issue.suggestion}</div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
