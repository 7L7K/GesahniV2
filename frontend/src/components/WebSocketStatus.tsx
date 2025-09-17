'use client';

import { useState, useEffect } from 'react';
import { wsHub } from '@/services/wsHub';

interface WebSocketStatusProps {
    className?: string;
    showDetails?: boolean;
}

export function WebSocketStatus({ className = '', showDetails = false }: WebSocketStatusProps) {
    const [musicStatus, _setMusicStatus] = useState(() => wsHub.getConnectionStatus('music'));
    const [careStatus, _setCareStatus] = useState(() => wsHub.getConnectionStatus('care'));
    const [showFailureHint, setShowFailureHint] = useState(false);
    const [failureDetails, setFailureDetails] = useState<{ name: string; reason: string; timestamp: number } | null>(null);

    useEffect(() => {
        // DISABLED: Status polling should be controlled by orchestrator
        // Update status periodically
        // const interval = setInterval(() => {
        //     setMusicStatus(wsHub.getConnectionStatus('music'));
        //     setCareStatus(wsHub.getConnectionStatus('care'));
        // }, 1000);

        // Listen for connection failure events
        const handleConnectionFailed = (event: CustomEvent) => {
            const { name, reason, timestamp } = event.detail;
            setFailureDetails({ name, reason, timestamp });
            setShowFailureHint(true);

            // Auto-hide after 10 seconds
            setTimeout(() => {
                setShowFailureHint(false);
                setFailureDetails(null);
            }, 10000);
        };

        window.addEventListener('ws:connection_failed', handleConnectionFailed as EventListener);

        return () => {
            // clearInterval(interval);
            window.removeEventListener('ws:connection_failed', handleConnectionFailed as EventListener);
        };
    }, []);

    const getStatusColor = (status: { isOpen: boolean; isConnecting: boolean; failureReason: string | null }) => {
        if (status.isOpen) return 'bg-green-500';
        if (status.isConnecting) return 'bg-yellow-500';
        if (status.failureReason) return 'bg-red-500';
        return 'bg-gray-300';
    };

    const getStatusText = (status: { isOpen: boolean; isConnecting: boolean; failureReason: string | null }) => {
        if (status.isOpen) return 'Connected';
        if (status.isConnecting) return 'Connecting...';
        if (status.failureReason) return 'Failed';
        return 'Disconnected';
    };

    const formatFailureTime = (timestamp: number) => {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    };

    return (
        <div className={`flex flex-col gap-2 ${className}`}>
            {/* Connection Status Indicators */}
            <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${getStatusColor(musicStatus)}`}></div>
                    <span className="text-gray-600">Music WS: {getStatusText(musicStatus)}</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${getStatusColor(careStatus)}`}></div>
                    <span className="text-gray-600">Care WS: {getStatusText(careStatus)}</span>
                </div>
            </div>

            {/* Detailed Status (when showDetails is true) */}
            {showDetails && (
                <div className="text-xs text-gray-500 space-y-1">
                    {musicStatus.failureReason && (
                        <div>Music: {musicStatus.failureReason} at {formatFailureTime(musicStatus.lastFailureTime)}</div>
                    )}
                    {careStatus.failureReason && (
                        <div>Care: {careStatus.failureReason} at {formatFailureTime(careStatus.lastFailureTime)}</div>
                    )}
                </div>
            )}

            {/* Connection Failure Hint */}
            {showFailureHint && failureDetails && (
                <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm">
                    <div className="flex items-start gap-2">
                        <div className="w-2 h-2 bg-red-500 rounded-full mt-1.5 flex-shrink-0"></div>
                        <div className="flex-1">
                            <div className="font-medium text-red-800">
                                WebSocket Connection Failed
                            </div>
                            <div className="text-red-700 mt-1">
                                {failureDetails.name === 'music' ? 'Music' : 'Care'} connection failed: {failureDetails.reason}
                            </div>
                            <div className="text-red-600 text-xs mt-1">
                                Failed at {formatFailureTime(failureDetails.timestamp)}
                            </div>
                            <div className="text-red-600 text-xs mt-1">
                                Connection will not automatically retry. Please refresh the page to reconnect.
                            </div>
                        </div>
                        <button
                            onClick={() => setShowFailureHint(false)}
                            className="text-red-400 hover:text-red-600 text-lg leading-none"
                        >
                            ×
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
