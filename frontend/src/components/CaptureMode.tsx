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
  const [saving, setSaving] = useState(false);
  const [sessionMeta, setSessionMeta] = useState<{ status?: string; tags?: string[]; created_at?: string; errors?: string[] } | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      if (pollTimer.current) clearTimeout(pollTimer.current);
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
      try {
        const msg = JSON.parse(String(e.data || '')) as { text?: string; session_id?: string; error?: string };
        if (msg?.error) {
          console.error('ws: error message', msg.error);
          setError('Live transcription error.');
        }
        if (msg?.text) {
          // Backend sends the full running transcript; render it directly
          setCaptionText(msg.text);
        }
      } catch {
        // Fallback: treat as plain text
        const text = String(e.data || '').trim();
        if (text) setCaptionText(text);
      } finally {
        setShowIndicator(false);
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
    try {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send('end');
      }
    } catch { }
    wsRef.current?.close();
    await Promise.all([audioStopped, videoStopped]);
    setRecording(false);

    const audioBlob = new Blob(audioChunks.current, { type: audioMime });
    const videoBlob = new Blob(videoChunks.current, { type: videoMime });
    const form = new FormData();
    form.append('session_id', sessionIdRef.current || '');
    // Choose filenames consistent with MIME types to help backend/transcribers
    const audioFilename = audioMime.startsWith('audio/webm')
      ? 'audio.webm'
      : audioMime.startsWith('audio/mpeg')
        ? 'audio.mp3'
        : audioMime.startsWith('audio/mp4')
          ? 'audio.mp4'
          : 'audio.wav';
    const videoFilename = videoMime.startsWith('video/mp4') ? 'video.mp4' : 'video.webm';
    form.append('audio', audioBlob, audioFilename);
    form.append('video', videoBlob, videoFilename);
    if (captionText.trim()) {
      form.append('transcript', captionText.trim());
    }

    const sid = sessionIdRef.current;
    try {
      setSaving(true);
      await apiFetch('/v1/capture/save', { method: 'POST', body: form });
      console.log('stopRecording: capture saved');
      // Best-effort: trigger summarization to extract tags and summary
      if (sid) {
        try {
          await apiFetch(`/v1/sessions/${sid}/summarize`, { method: 'POST' });
        } catch (e) {
          console.warn('summarize failed (non-fatal)', e);
        }
      }
      // Poll capture status until DONE
      const poll = async () => {
        if (!sid) return;
        try {
          const res = await apiFetch(`/v1/capture/status/${sid}`, { method: 'GET' });
          if (!res.ok) return;
          const meta = await res.json();
          setSessionMeta(meta as { status?: string; tags?: string[]; created_at?: string; errors?: string[] });
          const statusVal = (meta as { status?: string } | null)?.status || '';
          const done = String(statusVal).toUpperCase() === 'DONE';
          if (!done) {
            pollTimer.current = setTimeout(poll, 2000);
          }
        } catch {
          // stop polling on error
          if (pollTimer.current) clearTimeout(pollTimer.current);
        } finally {
          setSaving(false);
        }
      };
      await poll();
    } catch (err) {
      console.error('failed to save capture', err);
      setError('Failed to save recording.');
      setSaving(false);
    }
  }, [audioMime, videoMime, captionText]);

  const newQuestion = () => setCaptionText('');
  const resetSession = () => {
    sessionIdRef.current = null;
    setCaptionText('');
    setSessionMeta(null);
    audioChunks.current = [];
    videoChunks.current = [];
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
        <Button onClick={setupStream} className="mt-2">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-sm border-b border-gray-200/50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">G</span>
            </div>
            <h1 className="text-xl font-semibold text-gray-800">Gesahni Capture</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <div className={`w-2 h-2 rounded-full ${recording ? 'bg-red-500 animate-pulse' : 'bg-gray-300'}`}></div>
              <span>{recording ? 'Live' : 'Ready'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col lg:flex-row gap-6 p-6">
        {/* Video section */}
        <div className="flex-1 relative group">
          <div className="relative rounded-2xl overflow-hidden shadow-2xl bg-black">
            <video
              ref={camRef}
              autoPlay
              muted
              className="w-full h-full object-cover"
              style={{ minHeight: '400px', maxHeight: '600px' }}
            />

            {/* Video overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>

            {/* Recording indicator */}
            {recording && (
              <div className="absolute top-4 right-4 flex items-center gap-2 bg-red-500/90 backdrop-blur-sm text-white px-4 py-2 rounded-full shadow-lg">
                <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
                <span className="text-sm font-medium">Recording</span>
                <div className="w-1 h-1 bg-white rounded-full animate-ping"></div>
              </div>
            )}

            {/* Video controls overlay */}
            <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <div className="bg-black/50 backdrop-blur-sm rounded-full p-2">
                <div className="w-6 h-6 bg-white rounded-full"></div>
              </div>
            </div>
          </div>

          {/* Audio level indicator */}
          <div className="absolute bottom-4 right-4 bg-black/50 backdrop-blur-sm rounded-full p-3">
            <div className="w-16 h-16 relative">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                <path
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="rgba(255,255,255,0.2)"
                  strokeWidth="2"
                />
                <path
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="white"
                  strokeWidth="2"
                  strokeDasharray={`${volume * 100}, 100`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-2 h-2 bg-white rounded-full"></div>
              </div>
            </div>
          </div>
        </div>

        {/* Transcription section */}
        <div className="flex-1 flex flex-col">
          <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 h-full min-h-[400px] lg:min-h-[500px] border border-gray-200/50">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-semibold text-gray-800 flex items-center gap-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                Live Transcription
              </h3>
              {captionText && (
                <button
                  onClick={newQuestion}
                  className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto">
              {captionText ? (
                <div className="space-y-3">
                  {captionText.split('\n').map((line, index) => (
                    <p key={index} className="text-gray-700 leading-relaxed text-lg">
                      {line}
                    </p>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                    <span className="text-2xl">🎤</span>
                  </div>
                  <p className="text-gray-500 text-lg mb-2">Ready to capture your thoughts</p>
                  <p className="text-gray-400 text-sm">Start recording to see live transcription</p>
                </div>
              )}

              {showIndicator && (
                <div className="flex items-center gap-3 mt-4 p-3 bg-blue-50 rounded-lg">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  </div>
                  <span className="text-blue-700 font-medium">Processing audio...</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Smart controls section */}
      <div className="bg-white/90 backdrop-blur-sm border-t border-gray-200/50 p-6">
        <div className="max-w-6xl mx-auto">
          {/* Main recording control */}
          <div className="flex justify-center mb-6">
            <div className="relative">
              {!recording ? (
                <button
                  onClick={startRecording}
                  className="group relative w-20 h-20 bg-gradient-to-r from-green-500 to-emerald-600 rounded-full shadow-2xl hover:shadow-green-500/25 transition-all duration-300 hover:scale-105 flex items-center justify-center"
                >
                  <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
                    <div className="w-0 h-0 border-l-[12px] border-l-white border-t-[8px] border-t-transparent border-b-[8px] border-b-transparent ml-1"></div>
                  </div>
                  <div className="absolute inset-0 rounded-full bg-white/20 animate-ping"></div>
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="group relative w-20 h-20 bg-gradient-to-r from-red-500 to-pink-600 rounded-full shadow-2xl hover:shadow-red-500/25 transition-all duration-300 hover:scale-105 flex items-center justify-center"
                >
                  <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
                    <div className="w-4 h-4 bg-red-500 rounded-sm"></div>
                  </div>
                </button>
              )}
            </div>
          </div>

          {/* Secondary controls */}
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={pauseRecording}
              disabled={!recording}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${recording
                ? 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                : 'bg-gray-50 text-gray-400 cursor-not-allowed'
                }`}
            >
              <span>⏸️</span>
              Pause
            </button>

            <button
              onClick={newQuestion}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 text-blue-700 hover:bg-blue-100 text-sm font-medium transition-all duration-200"
            >
              <span>🔄</span>
              New Session
            </button>

            <button
              onClick={resetSession}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-50 text-gray-700 hover:bg-gray-100 text-sm font-medium transition-all duration-200"
            >
              <span>🗑️</span>
              Reset
            </button>
          </div>

          {/* Smart hints */}
          <div className="mt-6 text-center">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-full">
              <span className="text-gray-400">💡</span>
              <span className="text-sm text-gray-600">
                Press <kbd className="px-2 py-1 bg-white rounded text-xs font-mono shadow-sm">Space</kbd> to toggle recording
              </span>
            </div>
            {(saving || sessionMeta) && (
              <div className="mt-4 flex flex-col items-center gap-2 text-sm text-gray-600">
                {saving && <span>Uploading…</span>}
                {sessionMeta && (
                  <>
                    <span>
                      Status: <strong>{sessionMeta.status || '—'}</strong>
                    </span>
                    {Array.isArray(sessionMeta.tags) && sessionMeta.tags.length > 0 && (
                      <div className="flex flex-wrap justify-center gap-2">
                        {sessionMeta.tags.map((t) => (
                          <span key={t} className="px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">#{t}</span>
                        ))}
                      </div>
                    )}
                    {Array.isArray(sessionMeta.errors) && sessionMeta.errors.length > 0 && (
                      <div className="text-red-600">Last error: {sessionMeta.errors[sessionMeta.errors.length - 1]}</div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
