"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, wsUrl } from "@/lib/api";
import { getAuthOrchestrator } from '@/services/authOrchestrator';

export type RecorderState =
    | { status: "idle"; error?: string }
    | { status: "arming" }
    | { status: "recording"; sessionId: string }
    | { status: "uploading"; sessionId: string }
    | { status: "error"; message: string };

export interface RecorderExports {
    state: RecorderState;
    volume: number;
    captionText: string;
    muted: boolean;
    wsOpen: boolean;
    elapsedMs: number;
    start: () => Promise<void>;
    pause: () => void;
    stop: () => Promise<void>;
    reset: () => void;
    toggleMute: () => void;
    setMuted: (b: boolean) => void;
    sendControl: (payload: Record<string, any>) => void;
    setDevices: (ids: { audio?: string; video?: string }) => void;
    audioOnly: boolean;
    setAudioOnly: (b: boolean) => void;
    media: { stream: MediaStream | null; videoEl: React.RefObject<HTMLVideoElement | null> };
}

export function useRecorder(): RecorderExports {
    const camRef = useRef<HTMLVideoElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const audioRecorder = useRef<MediaRecorder | null>(null);
    const videoRecorder = useRef<MediaRecorder | null>(null);
    const audioChunks = useRef<Blob[]>([]);
    const videoChunks = useRef<Blob[]>([]);
    const lastSend = useRef<number>(0);
    const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const connectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastStartAttemptRef = useRef<number>(0);
    const consecutiveConnectFailuresRef = useRef<number>(0);
    const breakerUntilRef = useRef<number>(0);

    const [state, setState] = useState<RecorderState>({ status: "idle" });
    const [volume, setVolume] = useState(0);
    const [captionText, setCaptionText] = useState("");
    const [muted, setMuted] = useState<boolean>(false);
    const [audioMime, setAudioMime] = useState<string>("");
    const [videoMime, setVideoMime] = useState<string>("");
    const [wsOpen, setWsOpen] = useState<boolean>(false);
    const [elapsedMs, setElapsedMs] = useState<number>(0);
    const [audioOnly, setAudioOnly] = useState<boolean>(false);
    const [deviceIds, setDeviceIds] = useState<{ audio?: string; video?: string }>({});
    const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        if (typeof MediaRecorder !== "undefined") {
            const aMime = MediaRecorder.isTypeSupported("audio/webm; codecs=opus")
                ? "audio/webm; codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm")
                    ? "audio/webm"
                    : "audio/mp4";
            const vMime = MediaRecorder.isTypeSupported('video/mp4; codecs="avc1.42E01E"')
                ? 'video/mp4; codecs="avc1.42E01E"'
                : MediaRecorder.isTypeSupported("video/mp4")
                    ? "video/mp4"
                    : "video/webm";
            setAudioMime(aMime);
            setVideoMime(vMime);
        }
    }, []);

    const setupStream = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: deviceIds.audio ? { deviceId: { exact: deviceIds.audio } as any } : true,
                video: deviceIds.video ? { deviceId: { exact: deviceIds.video } as any } : true,
            } as MediaStreamConstraints);
            streamRef.current = stream;
            if (camRef.current) camRef.current.srcObject = stream;
            const AudioCtx =
                window.AudioContext || (window as any).webkitAudioContext;
            const audioCtx = new AudioCtx();
            const source = audioCtx.createMediaStreamSource(stream);
            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 2048;
            source.connect(analyser);
            const dataArray = new Uint8Array(analyser.fftSize);
            const update = () => {
                analyser.getByteTimeDomainData(dataArray);
                let sum = 0;
                for (const v of dataArray) {
                    const norm = (v - 128) / 128;
                    sum += norm * norm;
                }
                setVolume(Math.sqrt(sum / dataArray.length));
                requestAnimationFrame(update);
            };
            update();
        } catch (e) {
            setState({ status: "error", message: "Please allow camera and microphone access." });
        }
    }, [deviceIds.audio, deviceIds.video]);

    useEffect(() => {
        setupStream();
        return () => {
            if (pollTimer.current) clearTimeout(pollTimer.current);
            if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
            try { audioRecorder.current?.stop(); } catch { }
            try { videoRecorder.current?.stop(); } catch { }
            try { wsRef.current?.close(); } catch { }
            try { streamRef.current?.getTracks().forEach(t => t.stop()); } catch { }
        };
    }, [setupStream]);

    const start = useCallback(async () => {
        // Circuit breaker: avoid spamming start when failing
        const now = Date.now();
        if (now < breakerUntilRef.current) {
            // quietly ignore attempts while breaker is active
            return;
        }
        // Debounce rapid toggles / double keypress
        if (now - lastStartAttemptRef.current < 1000) {
            return;
        }
        lastStartAttemptRef.current = now;
        if (state.status === 'arming' || state.status === 'recording') {
            return;
        }
        if (!streamRef.current) {
            await setupStream();
            if (!streamRef.current) return;
        }
        setState({ status: "arming" });
        let sessionId: string | undefined;
        try {
            const res = await apiFetch("/v1/capture/start", { method: "POST" });
            const data = await res.json();
            sessionId = data.session_id;
        } catch (e) {
            setState({ status: "error", message: "Failed to start recording." });
            return;
        }
        // Check authentication before creating WebSocket
        const authOrchestrator = getAuthOrchestrator();
        const authState = authOrchestrator.getState();

        if (!authState.is_authenticated) {
            setState({ status: "error", message: "Not authenticated. Please sign in to use recording features." });
            return;
        }

        // Health-gate the live transcription WS to avoid failing connects during outages
        try {
            const controller = new AbortController();
            const to = setTimeout(() => controller.abort(), 1500);
            const h = await apiFetch('/healthz/ready', { auth: false, dedupe: false, cache: 'no-store', signal: controller.signal });
            clearTimeout(to);
            const ok = h.ok && ((await h.json().catch(() => ({ status: 'fail' }))).status === 'ok');
            if (!ok) {
                setState({ status: "error", message: "Backend not ready. Please try again in a moment." });
                return;
            }
        } catch {
            setState({ status: "error", message: "Backend check failed. Please try again." });
            return;
        }

        const ws = new WebSocket(wsUrl("/v1/transcribe"));
        setWsOpen(false);
        ws.onopen = () => {
            if (connectTimerRef.current) { clearTimeout(connectTimerRef.current); connectTimerRef.current = null; }
            setWsOpen(true);
            consecutiveConnectFailuresRef.current = 0;
        };
        ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(String(e.data || ""));
                if (msg?.error) setState({ status: "error", message: msg.error === 'listening_network_shaky' ? 'Listening… network shaky' : 'Live transcription error.' });
                if (msg?.event === 'stt.partial' && msg?.text) setCaptionText(msg.text);
                if (msg?.event === 'stt.final' && msg?.text) setCaptionText(msg.text);
                // Optionally, we could show a subtle glow when TTS runs
                if (msg?.event === 'tts.start') {
                    document.body.classList.add('tts-active');
                }
                if (msg?.event === 'tts.stop') {
                    document.body.classList.remove('tts-active');
                }
            } catch {
                const text = String(e.data || "").trim();
                if (text) setCaptionText(text);
            }
        };
        ws.onclose = () => {
            setWsOpen(false);
            if (connectTimerRef.current) { clearTimeout(connectTimerRef.current); connectTimerRef.current = null; }
            // DO NOT call whoami on close - use global auth store instead
            // Surface connection failure for UI hint
            try {
                window.dispatchEvent(new CustomEvent("ws:connection_failed", {
                    detail: { name: "transcribe", reason: "Transcription connection lost", timestamp: Date.now() }
                }));
            } catch { /* noop */ }
        };
        ws.onerror = () => {
            // DO NOT call whoami on error - let onclose handle the logic
            try { ws.close(); } catch { /* noop */ }
        };
        wsRef.current = ws;

        // Press-to-talk: while holding space, send control messages
        const onKeyDown = (ev: KeyboardEvent) => {
            if (ev.code === 'Space' && ws.readyState === WebSocket.OPEN) {
                try { ws.send(JSON.stringify({ ptt: true })); } catch { }
            }
        };
        const onKeyUp = (ev: KeyboardEvent) => {
            if (ev.code === 'Space' && ws.readyState === WebSocket.OPEN) {
                try { ws.send(JSON.stringify({ ptt: false })); } catch { }
            }
        };
        window.addEventListener('keydown', onKeyDown);
        window.addEventListener('keyup', onKeyUp);

        // Short connect timeout: if not open within 4s, close and engage breaker after N failures
        if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
        connectTimerRef.current = setTimeout(() => {
            try { ws.close(); } catch { }
            setWsOpen(false);
            consecutiveConnectFailuresRef.current += 1;
            // After 3 rapid failures, back off for 30s
            if (consecutiveConnectFailuresRef.current >= 3) {
                breakerUntilRef.current = Date.now() + 30_000;
            }
        }, 4000);

        audioChunks.current = [];
        videoChunks.current = [];
        audioRecorder.current = new MediaRecorder(streamRef.current!, { mimeType: audioMime });
        videoRecorder.current = new MediaRecorder(streamRef.current!, { mimeType: videoMime });
        audioRecorder.current.ondataavailable = (e) => {
            if (e.data.size) {
                audioChunks.current.push(e.data);
                if (!muted && ws.readyState === WebSocket.OPEN) {
                    ws.send(e.data);
                    lastSend.current = Date.now();
                }
            }
        };
        videoRecorder.current.ondataavailable = (e) => { if (e.data.size) videoChunks.current.push(e.data); };
        audioRecorder.current.start(9000);
        videoRecorder.current.start();
        setState({ status: "recording", sessionId: sessionId! });
        // start elapsed timer
        if (tickRef.current) clearInterval(tickRef.current);
        const started = Date.now();
        setElapsedMs(0);
        tickRef.current = setInterval(() => setElapsedMs(Date.now() - started), 1000);
    }, [audioMime, videoMime, setupStream, state.status]);

    const pause = useCallback(() => {
        audioRecorder.current?.pause();
        videoRecorder.current?.pause();
        wsRef.current?.close();
        setState((s) => (s.status === "recording" ? { status: "idle" } : s));
        if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    }, []);

    const stop = useCallback(async () => {
        const sid = (state.status === "recording" || state.status === "uploading") ? state.sessionId : undefined;
        if (!sid) return;
        const audioStopped = new Promise<void>((resolve) => audioRecorder.current?.addEventListener("stop", () => resolve(), { once: true }));
        const videoStopped = new Promise<void>((resolve) => videoRecorder.current?.addEventListener("stop", () => resolve(), { once: true }));
        audioRecorder.current?.stop();
        videoRecorder.current?.stop();
        try { wsRef.current && wsRef.current.readyState === WebSocket.OPEN && wsRef.current.send("end"); } catch { }
        wsRef.current?.close();
        await Promise.all([audioStopped, videoStopped]);
        setState({ status: "uploading", sessionId: sid });

        const audioBlob = new Blob(audioChunks.current, { type: audioMime });
        const videoBlob = new Blob(videoChunks.current, { type: videoMime });
        const form = new FormData();
        form.append("session_id", sid);
        form.append("audio", audioBlob, audioMime.startsWith("audio/webm") ? "audio.webm" : audioMime.startsWith("audio/mpeg") ? "audio.mp3" : audioMime.startsWith("audio/mp4") ? "audio.mp4" : "audio.wav");
        form.append("video", videoBlob, videoMime.startsWith("video/mp4") ? "video.mp4" : "video.webm");
        if (captionText.trim()) form.append("transcript", captionText.trim());

        try {
            await apiFetch("/v1/capture/save", { method: "POST", body: form });
        } catch (e) {
            setState({ status: "error", message: "Failed to save recording." });
            return;
        }
        setState({ status: "idle" });
        if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
        setElapsedMs(0);
        // 8s inactivity settle timer
        const settleMs = 8000;
        setTimeout(() => {
            try {
                if (typeof window !== 'undefined' && window.location && document && window.location.pathname === '/capture') {
                    // Signal ambient mode; consumer can route or dim UI
                    const ev = new CustomEvent('ambient:settle');
                    window.dispatchEvent(ev);
                }
            } catch { }
        }, settleMs);
    }, [state, audioMime, videoMime, captionText]);

    const reset = useCallback(() => {
        setCaptionText("");
        audioChunks.current = [];
        videoChunks.current = [];
        setState({ status: "idle" });
        if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
        setElapsedMs(0);
    }, []);

    const stableSetDevices = useCallback((ids: { audio?: string; video?: string }) => {
        setDeviceIds((prev) => {
            const nextAudio = ids.audio || undefined;
            const nextVideo = ids.video || undefined;
            const unchanged = prev.audio === nextAudio && prev.video === nextVideo;
            return unchanged ? prev : { audio: nextAudio, video: nextVideo };
        });
    }, []);

    const sendControl = (payload: Record<string, any>) => {
        try { wsRef.current && wsRef.current.readyState === WebSocket.OPEN && wsRef.current.send(JSON.stringify(payload)); } catch { }
    };

    return {
        state,
        volume,
        captionText,
        muted,
        wsOpen,
        elapsedMs,
        start,
        pause,
        stop,
        reset,
        sendControl,
        toggleMute: () => setMuted(m => !m),
        setMuted,
        setDevices: stableSetDevices,
        audioOnly,
        setAudioOnly,
        media: { stream: streamRef.current, videoEl: camRef },
    };
}
