"use client";

import React, { Component, ReactNode } from 'react';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error?: Error;
    errorId?: string;
    errorTime?: string;
    componentStack?: string;
    errorBoundaryId?: string;
}

let errorCount = 0;

export class ErrorBoundary extends Component<Props, State> {
    private errorBoundaryId: string;

    constructor(props: Props) {
        super(props);
        this.errorBoundaryId = `eb_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        this.state = {
            hasError: false,
            errorBoundaryId: this.errorBoundaryId
        };
        console.info(`🛡️ ErrorBoundary ${this.errorBoundaryId} initialized`);
    }

    static getDerivedStateFromError(error: Error): State {
        const errorId = `error_${++errorCount}_${Date.now()}`;
        console.error(`🚨 ErrorBoundary static getDerivedStateFromError:`, {
            errorId,
            error: error.message,
            errorName: error.name,
            hasStack: !!error.stack,
            timestamp: new Date().toISOString()
        });
        return {
            hasError: true,
            error,
            errorId,
            errorTime: new Date().toISOString()
        };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        const errorId = this.state.errorId || `catch_${++errorCount}_${Date.now()}`;

        // Ultra-detailed error logging
        console.groupCollapsed(`💥 ERROR BOUNDARY ${this.errorBoundaryId} - ERROR #${errorCount}`);
        console.error('📋 ERROR SUMMARY:', {
            errorId,
            errorBoundaryId: this.errorBoundaryId,
            errorName: error.name,
            errorMessage: error.message,
            hasStack: !!error.stack,
            componentStackLength: errorInfo.componentStack?.length || 0,
            timestamp: new Date().toISOString(),
            userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
            url: typeof window !== 'undefined' ? window.location.href : 'unknown',
            isDev: process.env.NODE_ENV === 'development'
        });

        console.error('🔍 ERROR DETAILS:', {
            name: error.name,
            message: error.message,
            stack: error.stack,
            cause: (error as any).cause,
            timestamp: new Date().toISOString()
        });

        console.error('🏗️ COMPONENT STACK:', errorInfo.componentStack);

        // Log React-specific error info
        console.error('⚛️ REACT ERROR INFO:', {
            componentStack: errorInfo.componentStack?.split('\n').filter(line => line.trim())
        });

        // Log browser/environment context
        console.error('🌐 BROWSER CONTEXT:', {
            userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
            language: typeof navigator !== 'undefined' ? navigator.language : 'unknown',
            platform: typeof navigator !== 'undefined' ? navigator.platform : 'unknown',
            cookieEnabled: typeof navigator !== 'undefined' ? navigator.cookieEnabled : 'unknown',
            onLine: typeof navigator !== 'undefined' ? navigator.onLine : 'unknown',
            url: typeof window !== 'undefined' ? window.location.href : 'unknown',
            referrer: typeof document !== 'undefined' ? document.referrer : 'unknown'
        });

        // Log React state if available
        try {
            console.error('⚛️ REACT STATE:', {
                reactVersion: React.version,
                hasError: this.state.hasError,
                errorTime: this.state.errorTime,
                errorBoundaryId: this.errorBoundaryId
            });
        } catch (stateError) {
            console.error('❌ Could not log React state:', stateError);
        }

        console.groupEnd();

        // Store error details in state for display
        this.setState({
            componentStack: errorInfo.componentStack || '',
            errorId
        });

        // Global error tracking
        if (typeof window !== 'undefined') {
            (window as any).lastErrorBoundaryError = {
                errorId,
                errorBoundaryId: this.errorBoundaryId,
                error: {
                    name: error.name,
                    message: error.message,
                    stack: error.stack
                },
                componentStack: errorInfo.componentStack,
                timestamp: new Date().toISOString(),
                url: window.location.href,
                userAgent: navigator.userAgent
            };

            // Dispatch custom event for global error handling
            try {
                window.dispatchEvent(new CustomEvent('error-boundary-caught', {
                    detail: {
                        errorId,
                        errorBoundaryId: this.errorBoundaryId,
                        error: error.message,
                        timestamp: new Date().toISOString()
                    }
                }));
            } catch (eventError) {
                console.error('❌ Could not dispatch error event:', eventError);
            }
        }

        // You could also log to an error reporting service here
        // logErrorToService(error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
                    <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 text-center">
                        <div className="mb-4">
                            <div className="mx-auto w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
                                <svg className="w-8 h-8 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                                </svg>
                            </div>
                        </div>
                        <h1 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                            Something went wrong
                        </h1>
                        <p className="text-gray-600 dark:text-gray-400 mb-4">
                            We're sorry, but something unexpected happened. Please try refreshing the page.
                        </p>
                        <button
                            onClick={() => window.location.reload()}
                            className="inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
                        >
                            Refresh Page
                        </button>
                        {/* Enhanced error display for maximum debugging visibility */}
                        <div className="mt-4 space-y-2">
                            {/* Error ID and timestamp */}
                            <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                                Error ID: {this.state.errorId || 'unknown'} | Time: {this.state.errorTime || 'unknown'}
                            </div>

                            {/* Debug info always visible in dev, collapsible in prod */}
                            {(process.env.NODE_ENV === 'development' || this.state.error) && (
                                <details className="text-left">
                                    <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700 dark:text-gray-300 dark:hover:text-gray-100">
                                        🔍 Debug Info ({this.state.errorBoundaryId})
                                    </summary>
                                    <div className="mt-2 space-y-2">
                                        {/* Error details */}
                                        {this.state.error && (
                                            <div>
                                                <div className="text-xs font-semibold text-red-600 dark:text-red-400 mb-1">Error Details:</div>
                                                <pre className="text-xs bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-2 rounded overflow-auto max-h-32 text-red-800 dark:text-red-200">
                                                    {this.state.error.name}: {this.state.error.message}
                                                    {this.state.error.stack ? '\n\n' + this.state.error.stack : ''}
                                                </pre>
                                            </div>
                                        )}

                                        {/* Component stack */}
                                        {this.state.componentStack && (
                                            <div>
                                                <div className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-1">Component Stack:</div>
                                                <pre className="text-xs bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 p-2 rounded overflow-auto max-h-32 text-orange-800 dark:text-orange-200">
                                                    {this.state.componentStack}
                                                </pre>
                                            </div>
                                        )}

                                        {/* Environment info */}
                                        <div>
                                            <div className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-1">Environment:</div>
                                            <pre className="text-xs bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 p-2 rounded text-blue-800 dark:text-blue-200">
                                                {JSON.stringify({
                                                    reactVersion: React.version,
                                                    nodeEnv: process.env.NODE_ENV,
                                                    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
                                                    url: typeof window !== 'undefined' ? window.location.href : 'unknown',
                                                    timestamp: new Date().toISOString(),
                                                    errorBoundaryId: this.state.errorBoundaryId,
                                                    errorId: this.state.errorId
                                                }, null, 2)}
                                            </pre>
                                        </div>

                                        {/* Global error helper */}
                                        <div className="text-xs">
                                            <button
                                                onClick={() => {
                                                    if (typeof window !== 'undefined') {
                                                        const error = (window as any).lastErrorBoundaryError;
                                                        console.log('📋 Last Error Boundary Error:', error);
                                                        navigator.clipboard?.writeText(JSON.stringify(error, null, 2));
                                                        alert('Error details copied to clipboard and logged to console');
                                                    }
                                                }}
                                                className="px-2 py-1 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded text-xs hover:bg-gray-300 dark:hover:bg-gray-600"
                                            >
                                                Copy Error to Clipboard
                                            </button>
                                        </div>
                                    </div>
                                </details>
                            )}
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

// Hook-based error boundary for functional components
export function useErrorHandler() {
    return (error: Error, errorInfo?: { componentStack?: string }) => {
        console.error('Error caught by useErrorHandler:', error, errorInfo);
        // You could dispatch to a global error state here
    };
}
