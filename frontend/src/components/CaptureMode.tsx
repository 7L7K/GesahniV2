'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { getToken, isAuthed } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { RecorderProvider, useRecorderCtx } from './recorder/RecorderProvider';
import { RecorderControls } from './recorder/RecorderControls';
import { LevelMeter } from './recorder/LevelMeter';
import { LiveTranscript } from './recorder/LiveTranscript';
import { SessionTimeline } from './recorder/SessionTimeline';
import { DevicePicker } from './recorder/DevicePicker';
import FooterRibbon from '@/components/FooterRibbon';

function CaptureInner() {
  const rec = useRecorderCtx();
  const camRef = rec.media.videoEl;
  const router = useRouter();

  const recording = rec.state.status === 'recording';
  const [storyVoice, setStoryVoice] = useState(true);

  // Auth guard on client: require token in header mode
  useEffect(() => {
    try {
      if (!isAuthed() && !getToken()) {
        router.replace('/login');
        return;
      }
    } catch {
      /* ignore */
    }
  }, [router]);

  const startRecording = useCallback(async () => { await rec.start(); }, [rec]);
  const pauseRecording = useCallback(() => { rec.pause(); }, [rec]);
  const stopRecording = useCallback(async () => { await rec.stop(); }, [rec]);
  const newQuestion = () => rec.reset();
  const resetSession = () => rec.reset();

  // Keyboard shortcut: Space toggles start/stop
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

  // Error surface from recorder
  if (rec.state.status === 'error') {
    return (
      <>
        <div className="p-4">
          <p>{rec.state.message}</p>
          <Button onClick={newQuestion} className="mt-2">Retry</Button>
        </div>
        <FooterRibbon />
      </>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="bg-white/80 backdrop-blur-sm border-b border-gray-200/50 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">G</span>
            </div>
            <h1 className="text-xl font-semibold text-gray-800">Gesahni Capture</h1>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2 text-gray-600">
              <div className={`w-2 h-2 rounded-full ${recording ? 'bg-red-500 animate-pulse' : 'bg-gray-300'}`}></div>
              <span>{recording ? 'Live' : 'Ready'}</span>
            </div>
            <div className="flex items-center gap-2 text-gray-600">
              <div className={`w-2 h-2 rounded-full ${rec.wsOpen ? 'bg-green-500' : 'bg-gray-300'}`}></div>
              <span>{rec.wsOpen ? 'Connected' : 'Disconnected'}</span>
            </div>
            <div className="text-gray-600">
              {recording ? `Elapsed: ${Math.floor(rec.elapsedMs / 1000)}s` : 'Idle'}
            </div>
            <label className="flex items-center gap-2 text-gray-700">
              <input type="checkbox" checked={storyVoice} onChange={e => setStoryVoice(e.target.checked)} />
              Story Voice
            </label>
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row gap-6 p-6">
        <div className="flex-1 relative group">
          <div className="relative rounded-2xl overflow-hidden shadow-2xl bg-black">
            {rec.audioOnly ? (
              <div className="w-full h-[400px] flex items-center justify-center text-gray-200">Audio only</div>
            ) : (
              <video
                ref={camRef}
                autoPlay
                muted
                className="w-full h-full object-cover"
                style={{ minHeight: '400px', maxHeight: '600px' }}
              />
            )}

            <div className="absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>

            {recording && (
              <div className="absolute top-4 right-4 flex items-center gap-2 bg-red-500/90 backdrop-blur-sm text-white px-4 py-2 rounded-full shadow-lg">
                <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
                <span className="text-sm font-medium">Recording</span>
                <div className="w-1 h-1 bg-white rounded-full animate-ping"></div>
              </div>
            )}

            <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <div className="bg-black/50 backdrop-blur-sm rounded-full p-2">
                <div className="w-6 h-6 bg-white rounded-full"></div>
              </div>
            </div>
          </div>

          <div className="absolute bottom-4 right-4 bg-black/50 backdrop-blur-sm rounded-full p-3"><LevelMeter volume={rec.volume} /></div>
        </div>

        <div className="flex-1 flex flex-col">
          <LiveTranscript text={rec.captionText} onClear={newQuestion} />
        </div>
      </div>

      <div className="bg-white/90 backdrop-blur-sm border-t border-gray-200/50 p-6">
        <div className="max-w-6xl mx-auto">
          <div className="flex justify-center mb-6"><RecorderControls /></div>

          <div className="flex items-center justify-center gap-4">
            <button
              onClick={newQuestion}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 text-blue-700 hover:bg-blue-100 text-sm font-medium transition-all duration-200"
            >
              <span>🔄</span>
              New Session
            </button>

            {/* Single reset button below; remove duplicate to avoid query collisions */}
            <button
              onClick={resetSession}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-50 text-gray-700 hover:bg-gray-100 text-sm font-medium transition-all duration-200"
            >
              <span>🗑️</span>
              Reset
            </button>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={rec.audioOnly} onChange={e => rec.setAudioOnly(e.target.checked)} />
              Audio only
            </label>
            <DevicePicker onChange={rec.setDevices} />
          </div>

          <div className="mt-6 text-center">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-full">
              <span className="text-gray-400">💡</span>
              <span className="text-sm text-gray-600">
                Press <kbd className="px-2 py-1 bg-white rounded text-xs font-mono shadow-sm">Space</kbd> to toggle recording
              </span>
            </div>
            <SessionTimeline meta={null} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CaptureMode() {
  return (
    <RecorderProvider>
      <CaptureInner />
    </RecorderProvider>
  );
}

// Test-only named export
// eslint-disable-next-line import/no-unused-modules
export { CaptureInner as __TEST__CaptureInner };
