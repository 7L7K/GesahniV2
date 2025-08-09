'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { getToken, wsUrl, apiFetch } from '@/lib/api';
import { useRouter } from 'next/navigation';

// Determine supported mime types for media recording
// (defaults will be refined once the component mounts)
// initial types are kept local to setupStream/recorders

export default function CaptureMode() {
  // Refs and state
  const camRef = useRef<HTMLVideoElement>(null);
  const audioRecorder = useRef<MediaRecorder | null>(null);
  const videoRecorder = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const videoChunks = useRef<Blob[]>([]);
  const router = useRouter();

  const [captionText, setCaptionText] = useState('');
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState('');
  const [showIndicator, setShowIndicator] = useState(false);
  const lastSend = useRef<number>(0);
  const [volume, setVolume] = useState(0);

  // Dynamic MIME types
  const [audioMime, setAudioMime] = useState<string>('');
  const [videoMime, setVideoMime] = useState<string>('');

  useEffect(() => {
    if (typeof MediaRecorder !== 'undefined') {
      const aMime = MediaRecorder.isTypeSupported('audio/webm; codecs=opus')
        ? 'audio/webm; codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : 'audio/mp4';
      const vMime = MediaRecorder.isTypeSupported('video/mp4; codecs="avc1.42E01E"')
        ? 'video/mp4; codecs="avc1.42E01E"'
        : MediaRecorder.isTypeSupported('video/mp4')
          ? 'video/mp4'
          : 'video/webm';
      setAudioMime(aMime);
      setVideoMime(vMime);

      if (!aMime || !vMime) {
        console.error('No supported codecs – recording disabled');
      }
    }
  }, []);

  const setupStream = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      console.log('setupStream: obtained media stream', stream);
      streamRef.current = stream;
      if (camRef.current) camRef.current.srcObject = stream;

      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
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
    } catch (err) {
      console.error('setupStream: failed to get media stream', err);
      setError('Please allow camera and microphone access.');
    }
  }, []);

  useEffect(() => {
    // Hard guard: require token client-side; if missing, bounce to login
    if (!getToken()) {
      document.cookie = 'auth:hint=0; path=/; max-age=300';
      router.replace('/login?next=%2Fcapture');
      return;
    }
    setupStream();
    return () => {
      try {
        audioRecorder.current?.stop();
      } catch { }
      try {
        videoRecorder.current?.stop();
      } catch { }
      try {
        wsRef.current?.close();
      } catch { }
      try {
        streamRef.current?.getTracks().forEach(t => t.stop());
      } catch { }
    };
  }, [setupStream, router]);

  const startRecording = useCallback(async () => {
    if (!streamRef.current) {
      await setupStream();
      if (!streamRef.current) return;
    }
    console.log('startRecording: initiating session');
    try {
      const res = await apiFetch('/v1/capture/start', { method: 'POST' });
      if (!res.ok) throw new Error('start failed');
      const data = await res.json();
      sessionIdRef.current = data.session_id;
      console.log('startRecording: session started', sessionIdRef.current);
    } catch (err) {
      console.error('failed to start capture', err);
      setError('Failed to start recording.');
      return;
    }
    const ws = new WebSocket(wsUrl('/v1/transcribe'));
    ws.onopen = () => console.log('ws: opened');
    ws.onclose = () => console.log('ws: closed');
    ws.onerror = (e) => console.error('ws: error', e);
    ws.onmessage = (e) => {
      console.log('ws: message', e.data);
      setCaptionText((prev) => (prev ? prev + '\n' : '') + e.data);
      setShowIndicator(false);
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
          setTimeout(() => {
            if (Date.now() - lastSend.current > 1000) setShowIndicator(true);
          }, 1000);
        }
      }
    };

    videoRecorder.current.ondataavailable = (e) => {
      if (e.data.size) videoChunks.current.push(e.data);
    };

    audioRecorder.current.start(9000);
    videoRecorder.current.start();
    console.log('startRecording: recorders started');
    setRecording(true);
  }, [setupStream, audioMime, videoMime]);

  const pauseRecording = useCallback(() => {
    console.log('pauseRecording');
    audioRecorder.current?.pause();
    videoRecorder.current?.pause();
    wsRef.current?.close();
    setRecording(false);
  }, []);

  const stopRecording = useCallback(async () => {
    console.log('stopRecording');
    const audioStopped = new Promise<void>((resolve) => {
      audioRecorder.current?.addEventListener('stop', () => resolve(), { once: true });
    });
    const videoStopped = new Promise<void>((resolve) => {
      videoRecorder.current?.addEventListener('stop', () => resolve(), { once: true });
    });
    audioRecorder.current?.stop();
    videoRecorder.current?.stop();
    wsRef.current?.close();
    await Promise.all([audioStopped, videoStopped]);
    setRecording(false);

    const audioBlob = new Blob(audioChunks.current, { type: audioMime });
    const videoBlob = new Blob(videoChunks.current, { type: videoMime });
    const form = new FormData();
    form.append('session_id', sessionIdRef.current || '');
    form.append(
      'audio',
      audioBlob,
      audioMime === 'audio/webm' ? 'audio.webm' : 'audio.mp4'
    );
    form.append(
      'video',
      videoBlob,
      videoMime === 'video/mp4' ? 'video.mp4' : 'video.webm'
    );

    try {
      await apiFetch('/v1/capture/save', { method: 'POST', body: form });
      console.log('stopRecording: capture saved');
    } catch (err) {
      console.error('failed to save capture', err);
      setError('Failed to save recording.');
    }
  }, [audioMime, videoMime]);

  const newQuestion = () => setCaptionText('');

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        if (recording) {
          stopRecording();
        } else {
          startRecording();
        }
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [recording, startRecording, stopRecording]);

  if (error) {
    return (
      <div className="p-4">
        <p>{error}</p>
        <Button onClick={setupStream} className="mt-2">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="grid grid-cols-2 h-full">
        <video ref={camRef} autoPlay muted className="rounded-lg shadow" />
        <div className="p-4 overflow-y-auto">
          <p className="whisper-caption whitespace-pre-wrap">{captionText}</p>
          {showIndicator && <p className="text-sm text-gray-500">Transcribing…</p>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button onClick={startRecording} disabled={recording} variant="default">
          ▶️ Start Recording
        </Button>
        <Button onClick={pauseRecording} disabled={!recording} variant="secondary">
          ⏸️ Pause Recording
        </Button>
        <Button onClick={stopRecording} disabled={!recording} variant="destructive">
          ⏹️ Stop & Save
        </Button>
        <Button onClick={newQuestion} variant="default">
          🔄 New Question
        </Button>
        <div className="ml-4 w-24 h-2 bg-gray-300">
          <div
            className="h-full bg-green-500"
            style={{ width: `${Math.min(volume * 100, 100)}%` }}
          />
        </div>
      </div>
      <div className="mt-2 p-2 bg-gray-100 text-xs rounded">
        <pre>
          {JSON.stringify(
            {
              sessionId: sessionIdRef.current,
              recording,
              audioChunks: audioChunks.current.length,
              videoChunks: videoChunks.current.length,
              error,
            },
            null,
            2,
          )}
        </pre>
      </div>
    </div>
  );
}
