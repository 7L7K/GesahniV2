'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const audioMime = MediaRecorder.isTypeSupported('audio/webm')
  ? 'audio/webm'
  : 'audio/mp4';

const videoMime = MediaRecorder.isTypeSupported('video/mp4')
  ? 'video/mp4'
  : 'video/webm';

export default function CaptureMode() {
  const camRef = useRef<HTMLVideoElement>(null);
  const audioRecorder = useRef<MediaRecorder>();
  const videoRecorder = useRef<MediaRecorder>();
  const streamRef = useRef<MediaStream>();
  const wsRef = useRef<WebSocket>();
  const sessionIdRef = useRef<string | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const videoChunks = useRef<Blob[]>([]);
  const [captionText, setCaptionText] = useState('');
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState('');
  const [showIndicator, setShowIndicator] = useState(false);
  const lastSend = useRef<number>(0);
  const [volume, setVolume] = useState(0);

  const setupStream = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      if (camRef.current) {
        camRef.current.srcObject = stream;
      }
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      const audioCtx = new AudioCtx();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.fftSize);
      const update = () => {
        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const val = (dataArray[i] - 128) / 128;
          sum += val * val;
        }
        setVolume(Math.sqrt(sum / dataArray.length));
        requestAnimationFrame(update);
      };
      update();
    } catch {
      setError('Please allow camera and microphone access.');
    }
  }, []);

  useEffect(() => {
    setupStream();
  }, [setupStream]);

  const startRecording = useCallback(async () => {
    if (!streamRef.current) {
      await setupStream();
      if (!streamRef.current) return;
    }
    try {
      const res = await fetch('/capture/start', { method: 'POST' });
      if (!res.ok) throw new Error('start failed');
      const data = await res.json();
      sessionIdRef.current = data.session_id;
    } catch (err) {
      console.error('failed to start capture', err);
      setError('Failed to start recording.');
      return;
    }
    const ws = new WebSocket(`${window.location.origin.replace(/^http/, 'ws')}/transcribe`);
    ws.onmessage = (e) => {
      setCaptionText((prev) => (prev ? prev + '\n' : '') + e.data);
      setShowIndicator(false);
    };
    wsRef.current = ws;
    audioChunks.current = [];
    videoChunks.current = [];
    audioRecorder.current = new MediaRecorder(streamRef.current!, { mimeType: audioMime });
    videoRecorder.current = new MediaRecorder(streamRef.current!, { mimeType: videoMime });
    audioRecorder.current.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.current.push(e.data);
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(e.data);
          lastSend.current = Date.now();
          setTimeout(() => {
            if (Date.now() - lastSend.current > 1000) {
              setShowIndicator(true);
            }
          }, 1000);
        }
      }
    };
    videoRecorder.current.ondataavailable = (e) => {
      if (e.data.size > 0) {
        videoChunks.current.push(e.data);
      }
    };
    audioRecorder.current.start(9000);
    videoRecorder.current.start();
    setRecording(true);
  }, [setupStream]);

  const pauseRecording = useCallback(() => {
    audioRecorder.current?.pause();
    videoRecorder.current?.pause();
    wsRef.current?.close();
    setRecording(false);
  }, []);

  const stopRecording = useCallback(async () => {
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
      audioMime === 'audio/webm' ? 'audio.webm' : 'audio.mp4',
    );
    form.append(
      'video',
      videoBlob,
      videoMime === 'video/mp4' ? 'video.mp4' : 'video.webm',
    );
    try {
      await fetch('/capture/save', { method: 'POST', body: form });
    } catch (err) {
      console.error('failed to save capture', err);
      setError('Failed to save recording.');
    }
  }, []);

  const newQuestion = () => {
    setCaptionText('');
  };

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
        <button
          onClick={setupStream}
          className="mt-2 px-3 py-1 bg-blue-500 text-white rounded"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="grid grid-cols-2 h-full">
        <video ref={camRef} autoPlay muted className="rounded-lg shadow" />
        <div className="p-4 overflow-y-auto">
          <p className="whisper-caption whitespace-pre-wrap">
            {captionText}
          </p>
          {showIndicator && <p className="text-sm text-gray-500">Transcribing…</p>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={startRecording} disabled={recording} className="px-2 py-1 bg-green-500 text-white rounded">▶️ Start Recording</button>
        <button onClick={pauseRecording} disabled={!recording} className="px-2 py-1 bg-yellow-500 text-white rounded">⏸️ Pause Recording</button>
        <button onClick={stopRecording} disabled={!recording} className="px-2 py-1 bg-red-500 text-white rounded">⏹️ Stop & Save</button>
        <button onClick={newQuestion} className="px-2 py-1 bg-blue-500 text-white rounded">🔄 New Question</button>
        <div className="ml-4 w-24 h-2 bg-gray-300">
          <div
            className="h-full bg-green-500"
            style={{ width: `${Math.min(volume * 100, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

