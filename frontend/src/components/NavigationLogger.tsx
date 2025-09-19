'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useRef, Suspense } from 'react';

function NavigationLoggerImpl() {
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const previousPathRef = useRef<string>('');

    useEffect(() => {
        const currentPath = pathname + (searchParams?.toString() ? `?${searchParams.toString()}` : '');
        const timestamp = new Date().toISOString();
        const previousPath = previousPathRef.current;

        if (previousPath !== currentPath) {
            console.log(`🧭 NAVIGATION: ${timestamp} | From: ${previousPath || 'initial'} | To: ${currentPath} | User-Agent: ${navigator.userAgent.substring(0, 50)}...`);

            // Log additional client-side info
            console.log(`📊 CLIENT_INFO: ${timestamp} | Viewport: ${window.innerWidth}x${window.innerHeight} | Online: ${navigator.onLine} | Language: ${navigator.language} | Timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`);

            previousPathRef.current = currentPath;
        }
    }, [pathname, searchParams]);

    // Log page load performance
    useEffect(() => {
        const logPerformance = () => {
            if (typeof window !== 'undefined' && 'performance' in window) {
                const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
                if (navigation) {
                    const loadTime = navigation.loadEventEnd - navigation.fetchStart;
                    const domContentLoaded = navigation.domContentLoadedEventEnd - navigation.fetchStart;
                    const timestamp = new Date().toISOString();

                    console.log(`⚡ PERF_LOAD: ${timestamp} | Path: ${pathname} | Total Load: ${Math.round(loadTime)}ms | DOM Ready: ${Math.round(domContentLoaded)}ms | DNS: ${Math.round(navigation.domainLookupEnd - navigation.domainLookupStart)}ms | TCP: ${Math.round(navigation.connectEnd - navigation.connectStart)}ms`);
                }
            }
        };

        // Log performance after page load
        if (document.readyState === 'complete') {
            logPerformance();
        } else {
            window.addEventListener('load', logPerformance);
            return () => window.removeEventListener('load', logPerformance);
        }
    }, [pathname]);

    return null; // This component doesn't render anything
}

export default function NavigationLogger() {
    return (
        <Suspense fallback={null}>
            <NavigationLoggerImpl />
        </Suspense>
    );
}
