import React from 'react';
import Link from 'next/link';
import { useAuthErrorHandler } from '@/hooks/useAuthErrorHandler';

/**
 * Example toast component for displaying auth errors
 * You can customize this to match your design system
 */
export function AuthErrorToast() {
    const { error, dismissError } = useAuthErrorHandler();

    if (!error) return null;

    return (
        <div className="fixed top-4 right-4 z-50 max-w-sm">
            <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-4">
                <div className="flex items-start justify-between">
                    <div className="flex-1">
                        <h4 className="text-sm font-semibold text-gray-900">
                            {error.title}
                        </h4>
                        <p className="text-sm text-gray-600 mt-1">
                            {error.message}
                        </p>
                    </div>
                    <button
                        onClick={dismissError}
                        className="ml-3 text-gray-400 hover:text-gray-600"
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                {error.action && (
                    <div className="mt-3">
                        {error.action.href ? (
                            <Link
                                href={error.action.href}
                                className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-md transition-colors"
                                onClick={dismissError}
                            >
                                {error.action.label}
                            </Link>
                        ) : (
                            <button
                                onClick={() => {
                                    error.action?.onClick?.();
                                    dismissError();
                                }}
                                className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-md transition-colors"
                            >
                                {error.action.label}
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

/**
 * Hook-based version for custom toast implementations
 * Usage in your existing toast system:
 * ```tsx
 * function MyToastContainer() {
 *   useAuthErrorListener({
 *     onAnyError: (error) => {
 *       toast.error(error.message, {
 *         action: error.type === 'spotify_connection_required' ? {
 *           label: 'Connect',
 *           onClick: () => navigate('/spotify/connect')
 *         } : undefined
 *       });
 *     }
 *   });
 *
 *   return null; // This component doesn't render anything
 * }
 * ```
 */
