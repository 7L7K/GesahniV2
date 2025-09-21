import { useRef, useEffect } from "react";

export function useOnce(fn: () => void) {
    const did = useRef(false);
    useEffect(() => {
        if (!did.current) {
            did.current = true;
            fn();
        }
    }, []);
}

// Debug logging utility for grouping component logs
export function useGroupedLogger(componentName: string, enabled: boolean = true) {
    const renderSeq = useRef(0);

    const log = (message: string, data?: any) => {
        if (!enabled) return;

        const DEBUG_FETCH = process.env.NEXT_PUBLIC_DEBUG_FETCH === "true";
        if (!DEBUG_FETCH) return;

        renderSeq.current++;
        console.groupCollapsed(`[${componentName}] ${message} #${renderSeq.current}`);
        if (data) {
            console.log(data);
        }
        console.groupEnd();
    };

    return { log };
}
