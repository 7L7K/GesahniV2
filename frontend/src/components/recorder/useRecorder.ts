"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, wsUrl } from "@/lib/api";

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
    start: () => Promise<void>;
    pause: () => void;
    stop: () => Promise<void>;
    reset: () => void;
    media: { stream: MediaStream | null; videoEl: React.RefObject<HTMLVideoElement> };
}

export function useRecorder(): RecorderExports {
    const camRef = useRef<HTMLVideoElement>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const audioRecorder = useRef<MediaRecorder | null>(null);
    const videoRecorder = useRef<MediaRecorder | null>(null);
    const audioChunks = useRef<Blob[]>([]);
    const videoChunks = useRef<Blob[]>([]);
    const lastSend = useRef<number>(0);
    const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const [state, setState] = useState<RecorderState>({ status: "idle" });
    const [volume, setVolume] = useState(0);
    const [captionText, setCaptionText] = useState("");
    const [audioMime, setAudioMime] = useState<string>("");
    const [videoMime, setVideoMime] = useState<string>("");

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
            const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
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
    }, []);

    useEffect(() => {
        setupStream();
        return () => {
            if (pollTimer.current) clearTimeout(pollTimer.current);
            try { audioRecorder.current?.stop(); } catch { }
            try { videoRecorder.current?.stop(); } catch { }
            try { wsRef.current?.close(); } catch { }
            try { streamRef.current?.getTracks().forEach(t => t.stop()); } catch { }
        };
    }, [setupStream]);

    const start = useCallback(async () => {
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
        const ws = new WebSocket(wsUrl("/v1/transcribe"));
        ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(String(e.data || ""));
                if (msg?.error) setState({ status: "error", message: "Live transcription error." });
                if (msg?.text) setCaptionText(msg.text);
            } catch {
                const text = String(e.data || "").trim();
                if (text) setCaptionText(text);
            }
        };
        wsRef.current = ws;

        audioChunks.current = [];
        videoChunks.current = [];
        audioRecorder.current = new MediaRecorder(streamRef.current!, { mimeType: audioMime });
        videoRecorder.current = new MediaRecorder(streamRef.current!, { mimeType: videoMime });
        audioRecorder.current.ondataavailable = (e) => {
            if (e.data.size) {
                audioChunks.current.push(e.data);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(e.data);
                    lastSend.current = Date.now();
                }
            }
        };
        videoRecorder.current.ondataavailable = (e) => { if (e.data.size) videoChunks.current.push(e.data); };
        audioRecorder.current.start(9000);
        videoRecorder.current.start();
        setState({ status: "recording", sessionId: sessionId! });
    }, [audioMime, videoMime, setupStream]);

    const pause = useCallback(() => {
        audioRecorder.current?.pause();
        videoRecorder.current?.pause();
        wsRef.current?.close();
        setState((s) => (s.status === "recording" ? { status: "idle" } : s));
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
    }, [state, audioMime, videoMime, captionText]);

    const reset = useCallback(() => {
        setCaptionText("");
        audioChunks.current = [];
        videoChunks.current = [];
        setState({ status: "idle" });
    }, []);

    return {
        state,
        volume,
        captionText,
        start,
        pause,
        stop,
        reset,
        media: { stream: streamRef.current, videoEl: camRef },
    };
}


