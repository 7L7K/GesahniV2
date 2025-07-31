// frontend/src/components/CaptureMode.tsx
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export default function CaptureMode() {
  const camRef = useRef<HTMLVideoElement>(null);
  const audioRecorder = useRef<MediaRecorder>();
  const videoRecorder = useRef<MediaRecorder>();
  const streamRef = useRef<MediaStream>();
  const wsRef = useRef<WebSocket>();
  const audioChunks = useRef<Blob[]>([]);
  const videoChunks = useRef<Blob[]>([]);
  const [captionText, setCaptionText] = useState('');
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState('');
  const [showIndicator, setShowIndicator] = useState(false);
  const lastSend = useRef<number>(0);
  const [volume, setVolume] = useState(0);

  const [audioMime, setAudioMime] = useState<'audio/webm; codecs=opus' | 'audio/mp4'>('audio/mp4');
  const [videoMime, setVideoMime] = useState<'video/mp4; codecs="avc1.42E01E"' | 'video/webm; codecs=vp9'>(
    'video/webm; codecs=vp9'
  );
  useEffect(() => {
    if (typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined') {
      setAudioMime(
        MediaRecorder.isTypeSupported('audio/webm; codecs=opus') ? 'audio/webm; codecs=opus' : 'audio/mp4'
      );
      setVideoMime(
        MediaRecorder.isTypeSupported('video/mp4; codecs="avc1.42E01E"')
          ? 'video/mp4; codecs="avc1.42E01E"'
          : 'video/webm; codecs=vp9'
      );
    }
  }, []);

  const setupStream = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      if (camRef.current) camRef.current.srcObject = stream;

      const AudioCtx =
        window.AudioContext ||
        (window as any).webkitAudioContext;
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

    await fetch('/capture/start', { method: 'POST' });

    // direct WS to FastAPI
    const ws = new WebSocket('ws://localhost:8000/transcribe');
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
    setRecording(true);
  }, [setupStream, audioMime, videoMime]);

  const pauseRecording = useCallback(() => {
    audioRecorder.current?.pause();
    videoRecorder.current?.pause();
    wsRef.current?.close();
    setRecording(false);
  }, []);

  const stopRecording = useCallback(async () => {
    audioRecorder.current?.stop();
    videoRecorder.current?.stop();
    wsRef.current?.close();
    setRecording(false);

    const audioBlob = new Blob(audioChunks.current, { type: audioMime });
    const videoBlob = new Blob(videoChunks.current, { type: videoMime });
    const form = new FormData();
    form.append('audio', audioBlob, 'audio.webm');
    form.append('video', videoBlob, 'video.mp4');
    await fetch('/capture/save', { method: 'POST', body: form });
  }, [audioMime, videoMime]);

  const newQuestion = () => setCaptionText('');

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        recording ? stopRecording() : startRecording();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [recording, startRecording, stopRecording]);

  if (error) {
    return (
      <div className="p-4">
        <p>{error}</p>
        <button onClick={setupStream} className="mt-2 px-3 py-1 bg-blue-500 text-white rounded">
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
          <p className="whisper-caption whitespace-pre-wrap">{captionText}</p>
          {showIndicator && <p className="text-sm text-gray-500">Transcribing…</p>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={startRecording}
          disabled={recording}
          className="px-2 py-1 bg-green-500 text-white rounded"
        >
          ▶️ Start Recording
        </button>
        <button
          onClick={pauseRecording}
          disabled={!recording}
          className="px-2 py-1 bg-yellow-500 text-white rounded"
        >
          ⏸️ Pause Recording
        </button>
        <button
          onClick={stopRecording}
          disabled={!recording}
          className="px-2 py-1 bg-red-500 text-white rounded"
        >
          ⏹️ Stop & Save
        </button>
        <button onClick={newQuestion} className="px-2 py-1 bg-blue-500 text-white rounded">
          🔄 New Question
        </button>
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
