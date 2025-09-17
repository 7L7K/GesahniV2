"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function MusicMetrics() {
    const [token, setToken] = useState('');
    const [prometheusData, setPrometheusData] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();

    useEffect(() => {
        const envTok = process.env.NEXT_PUBLIC_ADMIN_TOKEN || '';
        const lsTok = typeof window !== 'undefined' ? (localStorage.getItem('admin:token') || '') : '';
        setToken(envTok || lsTok);
    }, []);

    const fetchMetrics = async () => {
        if (!token) {
            setError('No admin token provided');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await fetch('/metrics', {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'text/plain',
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.text();
            setPrometheusData(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch metrics');
            setPrometheusData('');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (token) {
            fetchMetrics();
        }
    }, [token]);

    const getMusicMetrics = () => {
        if (!prometheusData) return {};

        const lines = prometheusData.split('\n');
        const musicMetrics: Record<string, any> = {};

        // Parse music-related metrics
        const musicMetricNames = [
            'spotify_devices_request_count_total',
            'spotify_devices_cache_bypass_count_total',
            'spotify_status_requests_count_total',
            'spotify_device_list_count_total',
            'spotify_play_count_total',
            'music_command_total',
            'music_command_latency_seconds',
            'music_state_request_total',
            'music_set_device_total',
            'tv_music_play_total',
            'ws_music_connections_total',
            'ws_music_messages_total',
            'music_cmd_latency_ms',
            'music_transfer_fail_total',
            'music_rate_limited_total',
            'music_first_sound_ms',
            'music_reco_hit_total',
            'music_reco_miss_total'
        ];

        for (const line of lines) {
            if (line.startsWith('#') || !line.trim()) continue;

            const [name, value, ...labels] = line.split(/[{} ]/);

            if (musicMetricNames.some(metric => name.startsWith(metric))) {
                if (!musicMetrics[name]) {
                    musicMetrics[name] = [];
                }

                // Parse labels if present
                let parsedLabels: Record<string, string> = {};
                if (labels.length > 1 && labels[0]) {
                    const labelStr = labels[0];
                    if (labelStr.includes(',')) {
                        labelStr.split(',').forEach(label => {
                            const [key, val] = label.split('=');
                            if (key && val) {
                                parsedLabels[key.replace(/"/g, '')] = val.replace(/"/g, '');
                            }
                        });
                    } else {
                        const [key, val] = labelStr.split('=');
                        if (key && val) {
                            parsedLabels[key.replace(/"/g, '')] = val.replace(/"/g, '');
                        }
                    }
                }

                musicMetrics[name].push({
                    value: parseFloat(value),
                    labels: parsedLabels
                });
            }
        }

        return musicMetrics;
    };

    const musicMetrics = getMusicMetrics();

    const formatValue = (value: number) => {
        return value.toLocaleString();
    };

    const getTotalForMetric = (metricName: string) => {
        const data = musicMetrics[metricName];
        if (!data) return 0;
        return data.reduce((sum: number, item: any) => sum + item.value, 0);
    };

    return (
        <div className="mx-auto max-w-7xl p-6 space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold">Music Observability Dashboard</h1>
                    <p className="text-muted-foreground mt-2">
                        Monitor Spotify integration and music functionality
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => router.push('/admin/metrics')}
                        className="px-4 py-2 border rounded hover:bg-gray-50"
                    >
                        General Metrics
                    </button>
                    <button
                        onClick={fetchMetrics}
                        disabled={loading}
                        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                        {loading ? 'Loading...' : 'Refresh'}
                    </button>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 border border-red-200 rounded p-4">
                    <div className="flex items-center">
                        <div className="text-red-800 font-medium">Error:</div>
                        <div className="ml-2 text-red-700">{error}</div>
                    </div>
                </div>
            )}

            {/* Auth State Overview */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-green-600">
                        {formatValue(getTotalForMetric('spotify_devices_request_count_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">Device Requests</div>
                </div>

                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-blue-600">
                        {formatValue(getTotalForMetric('spotify_status_requests_count_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">Status Requests</div>
                </div>

                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-orange-600">
                        {formatValue(getTotalForMetric('spotify_devices_cache_bypass_count_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">Cache Bypasses</div>
                </div>

                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-purple-600">
                        {formatValue(getTotalForMetric('spotify_play_count_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">Play Requests</div>
                </div>

                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-indigo-600">
                        {formatValue(getTotalForMetric('music_command_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">Music Commands</div>
                </div>

                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-cyan-600">
                        {formatValue(getTotalForMetric('ws_music_connections_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">WS Connections</div>
                </div>

                <div className="bg-white rounded-lg border p-6">
                    <div className="text-2xl font-bold text-pink-600">
                        {formatValue(getTotalForMetric('tv_music_play_total'))}
                    </div>
                    <div className="text-sm text-muted-foreground">TV Play Requests</div>
                </div>
            </div>

            {/* Detailed Metrics */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Request Breakdown by Auth State */}
                <div className="bg-white rounded-lg border p-6">
                    <h3 className="text-lg font-semibold mb-4">Requests by Auth State</h3>
                    <div className="space-y-4">
                        {musicMetrics['spotify_devices_request_count_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Device {item.labels.status} ({item.labels.auth_state})
                                </div>
                                <div className="font-mono text-sm">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}
                        {musicMetrics['spotify_status_requests_count_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Status {item.labels.status} ({item.labels.auth_state})
                                </div>
                                <div className="font-mono text-sm">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}

                        {musicMetrics['music_command_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Cmd {item.labels.command} {item.labels.status} ({item.labels.provider})
                                </div>
                                <div className="font-mono text-sm">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}

                        {musicMetrics['music_state_request_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    State {item.labels.status} (cached:{item.labels.cached})
                                </div>
                                <div className="font-mono text-sm">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Performance Metrics */}
                <div className="bg-white rounded-lg border p-6">
                    <h3 className="text-lg font-semibold mb-4">Performance Metrics</h3>
                    <div className="space-y-4">
                        {musicMetrics['music_cmd_latency_ms']?.length > 0 && (
                            <div className="text-sm">
                                <div className="font-medium">Command Latency p95:</div>
                                <div className="font-mono">
                                    {musicMetrics['music_cmd_latency_ms'].reduce((sum: number, item: any) =>
                                        sum + item.value, 0
                                    ).toFixed(1)} ms
                                </div>
                            </div>
                        )}

                        {musicMetrics['music_first_sound_ms']?.length > 0 && (
                            <div className="text-sm">
                                <div className="font-medium">First Sound Latency p95:</div>
                                <div className="font-mono">
                                    {musicMetrics['music_first_sound_ms'].reduce((sum: number, item: any) =>
                                        sum + item.value, 0
                                    ).toFixed(1)} ms
                                </div>
                            </div>
                        )}

                        {musicMetrics['music_command_latency_seconds']?.length > 0 && (
                            <div className="text-sm">
                                <div className="font-medium">Command Latency p95:</div>
                                <div className="font-mono">
                                    {musicMetrics['music_command_latency_seconds'].reduce((sum: number, item: any) =>
                                        sum + item.value, 0
                                    ).toFixed(3)} s
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Error Tracking */}
                <div className="bg-white rounded-lg border p-6">
                    <h3 className="text-lg font-semibold mb-4">Error Tracking</h3>
                    <div className="space-y-4">
                        {musicMetrics['music_transfer_fail_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Transfer Fail ({item.labels.reason || 'unknown'})
                                </div>
                                <div className="font-mono text-sm text-red-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}

                        {musicMetrics['music_rate_limited_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Rate Limited ({item.labels.provider || 'unknown'})
                                </div>
                                <div className="font-mono text-sm text-orange-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}

                        {musicMetrics['music_set_device_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Set Device {item.labels.status}
                                </div>
                                <div className="font-mono text-sm text-blue-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* WebSocket Metrics */}
                <div className="bg-white rounded-lg border p-6">
                    <h3 className="text-lg font-semibold mb-4">WebSocket Activity</h3>
                    <div className="space-y-4">
                        {musicMetrics['ws_music_connections_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    WS {item.labels.action}
                                </div>
                                <div className="font-mono text-sm text-green-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}

                        {musicMetrics['ws_music_messages_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    WS {item.labels.direction} {item.labels.message_type}
                                </div>
                                <div className="font-mono text-sm text-purple-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recommendation Cache */}
                <div className="bg-white rounded-lg border p-6">
                    <h3 className="text-lg font-semibold mb-4">Recommendation Cache</h3>
                    <div className="space-y-4">
                        {musicMetrics['music_reco_hit_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Cache Hit ({item.labels.vibe || 'unknown'})
                                </div>
                                <div className="font-mono text-sm text-green-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}

                        {musicMetrics['music_reco_miss_total']?.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center">
                                <div className="text-sm">
                                    Cache Miss ({item.labels.vibe || 'unknown'})
                                </div>
                                <div className="font-mono text-sm text-orange-600">
                                    {formatValue(item.value)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Raw Prometheus Data */}
            {prometheusData && (
                <div className="bg-white rounded-lg border p-6">
                    <h3 className="text-lg font-semibold mb-4">Raw Prometheus Metrics</h3>
                    <details className="cursor-pointer">
                        <summary className="text-sm text-muted-foreground hover:text-foreground">
                            Click to view raw metrics data
                        </summary>
                        <pre className="text-xs mt-4 p-4 bg-gray-50 rounded overflow-auto max-h-96 whitespace-pre-wrap">
                            {prometheusData}
                        </pre>
                    </details>
                </div>
            )}

            {/* Instructions */}
            <div className="bg-blue-50 border border-blue-200 rounded p-6">
                <h3 className="text-lg font-semibold text-blue-900 mb-2">How to Access Full Grafana Dashboard</h3>
                <div className="text-blue-800 space-y-2">
                    <p>1. Start your monitoring stack:</p>
                    <code className="block bg-blue-100 p-2 rounded text-sm font-mono">
                        cd monitoring && docker-compose up -d
                    </code>

                    <p>2. Access Grafana at: <a href="http://localhost:3001" className="underline">http://localhost:3001</a></p>
                    <p>3. Import the "Music Observability Dashboard" from the dashboards directory</p>
                    <p>4. Access Prometheus metrics directly at: <a href="/metrics" className="underline">/metrics</a></p>
                </div>
            </div>
        </div>
    );
}
