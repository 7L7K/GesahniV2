'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ChatBubble from '../components/ChatBubble';
import LoadingBubble from '../components/LoadingBubble';
import InputBar from '../components/InputBar';
import { Button } from '@/components/ui/button';
// Clerk auth UI removed for cookie-only frontend
import { sendPrompt, getToken, getMusicState, type MusicState, apiFetch, isAuthed, handleAuthError } from '@/lib/api';
import { wsHub } from '@/services/wsHub';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import NowPlayingCard from '@/components/music/NowPlayingCard';
import DiscoveryCard from '@/components/music/DiscoveryCard';
import MoodDial from '@/components/music/MoodDial';
import QueueCard from '@/components/music/QueueCard';
import DevicePicker from '@/components/music/DevicePicker';
import { RateLimitToast, AuthMismatchToast } from '@/components/ui/toast';
import { WebSocketStatus } from '@/components/WebSocketStatus';
import { useAuthState, useAuthOrchestrator } from '@/hooks/useAuth';
import { useBootstrapManager } from '@/hooks/useBootstrap';
import { useWsOpen } from '@/hooks/useWs';
import Link from 'next/link';
import StatusBanner from '@/components/StatusBanner';
import WsIndicator from '@/components/WsIndicator';
import { ModelSelector } from '@/components/ModelSelector';
import EmptyState from '@/components/EmptyState';
import { useHealthPolling } from '@/hooks/useHealth';
import { useSpotifyStatus, useMusicDevices } from '@/hooks/useSpotify';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
}

// Clerk completely removed - using cookie authentication only

export default function Page() {
  // Guard rendering to avoid SSR/CSR markup mismatch: render a deterministic
  // placeholder on the server and mount the full interactive UI only on the
  // client. This prevents hydration errors caused by client-only APIs
  // (navigator/localStorage/window) that run during mount.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const router = useRouter();
  const authState = useAuthState();
  const authOrchestrator = useAuthOrchestrator();
  const bootstrapManager = useBootstrapManager();
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [sessionReady, setSessionReady] = useState<boolean>(false);
  // Backend status banner moved to StatusBanner component

  const authBootOnce = useRef<boolean>(false);
  const finishOnceRef = useRef<boolean>(false);
  const [finishBusy, setFinishBusy] = useState<boolean>(false);
  const [finishError, setFinishError] = useState<string | null>(null);
  const finishAbortRef = useRef<AbortController | null>(null);
  const prevReadyRef = useRef<boolean>(false);
  const prevBackendOnlineRef = useRef<boolean | null>(null);
  // Clerk removed - using only cookie auth

  // Use centralized auth state
  const authed = authState.is_authenticated;

  // Cookie mode only - show auth UI based on backend auth state
  const shouldShowAuthButtons = !authed;

  // Model state
  const [model, setModel] = useState<string>('auto');

  // Use centralized whoamiOk state from auth orchestrator instead of local debounced state
  const whoamiOk = authState.whoamiOk;

  const createInitialMessage = (): ChatMessage => ({
    id: crypto.randomUUID(),
    role: 'assistant',
    content: "Hey King, what's good?",
  });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [musicState, setMusicState] = useState<MusicState | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  // 'auto' lets the backend route to skills/LLM; user can still force a model
  const bottomRef = useRef<HTMLDivElement>(null);
  const musicStateFetchAttempted = useRef<boolean>(false);
  const { health, llamaDegraded } = useHealthPolling(15000);
  const [modelHint, setModelHint] = useState<string | null>(null);
  const wsMusicOpen = useWsOpen('music', 2000);
  const spotifyOk = (String(health?.checks?.spotify || 'ok') === 'ok') || (String(health?.checks?.spotify || '') === 'skipped');
  const { connected: spotifyConnected } = useSpotifyStatus(45000);
  const { hasDevice } = useMusicDevices(45000);
  const musicUiReady = wsMusicOpen && spotifyOk && spotifyConnected;
  const shouldPollHttpMusic = (!wsMusicOpen) && spotifyOk && spotifyConnected;
  const musicDegradedReason = !spotifyConnected ? 'Connect Spotify to enable playback' : (!spotifyOk ? 'Spotify degraded' : (!wsMusicOpen ? 'Connection lost — trying to reconnect' : (!hasDevice ? 'No device available' : 'Unavailable')));

  // Helpers: scope storage keys per user id for privacy
  const historyKey = `chat_history_${authState.user?.id || 'anon'}`;
  const modelKey = `selected_model_${authState.user?.id || 'anon'}`;

  // Update session ready based on centralized auth state
  useEffect(() => {
    setSessionReady(authState.session_ready);
  }, [authState.session_ready]);

  // Initialize bootstrap and auth state on mount
  useEffect(() => {
    if (authBootOnce.current) return;
    authBootOnce.current = true;

    // Initialize bootstrap manager first
    bootstrapManager.initialize().then((success) => {
      if (success) {
        console.info('Page: Bootstrap manager initialized successfully');
      } else {
        console.error('Page: Bootstrap manager initialization failed');
      }
    });

    // Initialize Auth Orchestrator
    authOrchestrator.initialize().then(() => {
      console.info('Page: Auth Orchestrator initialized successfully');
    }).catch((error) => {
      console.error('Page: Auth Orchestrator initialization failed:', error);
    });

    // Check for header token
    const hasHeaderToken = Boolean(getToken());
    if (hasHeaderToken) {
      setSessionReady(true);
    }

    setIsOnline(navigator.onLine);
    const onUp = () => setIsOnline(true);
    const onDown = () => setIsOnline(false);
    window.addEventListener('online', onUp);
    window.addEventListener('offline', onDown);
    const stored = localStorage.getItem(historyKey);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        // Validate that parsed data has the correct structure
        if (Array.isArray(parsed)) {
          type StoredMessage = Partial<ChatMessage> & { content?: unknown; role?: unknown };
          const validMessages: ChatMessage[] = (parsed as StoredMessage[])
            .filter((m) => m && typeof m === 'object' &&
              typeof m.content === 'string' &&
              (m.role === 'user' || m.role === 'assistant'))
            .map((m) => ({
              id: m.id ?? crypto.randomUUID(),
              role: m.role as 'user' | 'assistant',
              content: m.content as string,
              loading: Boolean(m.loading)
            }));
          setMessages(validMessages);
        }
      } catch (error) {
        console.error('Failed to parse stored messages:', error);
      }
    }

    return () => {
      window.removeEventListener('online', onUp);
      window.removeEventListener('offline', onDown);
      // Cleanup Auth Orchestrator
      authOrchestrator.cleanup();
    };
  }, [bootstrapManager, authOrchestrator]);

  // React to auth token changes (login/logout in other tabs)
  useEffect(() => {
    const handleStorageChange = () => {
      // Token changes are handled by the auth orchestrator
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Cookie mode: session ready based on backend auth state only
  useEffect(() => {
    const ready = Boolean(authed && whoamiOk);
    if (ready !== sessionReady) {
      setSessionReady(ready);
    }
  }, [authed, whoamiOk, sessionReady]);

  // Removed Clerk auth finish handling - using cookie auth only

  // Music state management
  useEffect(() => {
    if (!authed) {
      musicStateFetchAttempted.current = false;
      return;
    }

    const fetchMusicState = async (retryCount = 0) => {
      try {
        // Pre-check authentication status
        if (!authed) {
          console.warn('Skipping music state fetch - not authenticated');
          return;
        }

        const state = await getMusicState();
        setMusicState(state);
        musicStateFetchAttempted.current = true;
        setAuthError(null); // Clear any auth errors on success
      } catch (error) {
        console.error('Failed to fetch music state:', error);

        // Handle authentication errors
        if (error instanceof Error) {
          const errorMessage = error.message;

          // Check if this is an authentication error
          if (errorMessage.includes('Unauthorized') || errorMessage.includes('401')) {
            setAuthError('Authentication required. Please sign in to access music features.');

            // Only retry once and with longer delay to prevent rate limiting
            if (retryCount < 1) {
              console.info('Retrying music state fetch after auth refresh');
              setTimeout(() => {
                fetchMusicState(retryCount + 1);
              }, 3000); // Increased from 1000 to 3000ms to reduce rate limiting
            }
            return;
          }

          // Handle other errors
          await handleAuthError(error, 'music state fetch');
        }
      }
    };

    // Only fetch if we haven't already attempted or if auth state changed
    if (!musicStateFetchAttempted.current) {
      fetchMusicState();
    }

    // Listen for music state updates
    const handleMusicState = (event: CustomEvent) => {
      setMusicState(event.detail);
    };

    window.addEventListener('music.state', handleMusicState as EventListener);
    return () => {
      window.removeEventListener('music.state', handleMusicState as EventListener);
    };
  }, [authed, authOrchestrator]);

  // Listen for authentication state changes to retry music state fetch
  useEffect(() => {
    if (authed && !musicStateFetchAttempted.current) {
      // Auth was restored, retry music state fetch
      const fetchMusicState = async () => {
        try {
          const state = await getMusicState();
          setMusicState(state);
          musicStateFetchAttempted.current = true;
          setAuthError(null); // Clear any auth errors when successful
        } catch (error) {
          console.error('Failed to fetch music state after auth restore:', error);
          // Don't retry here to prevent oscillation - let the main effect handle it
        }
      };

      fetchMusicState();
    }
  }, [authed]);

  // Clear auth error when authentication is successful
  useEffect(() => {
    if (authed && authError) {
      setAuthError(null);
    }
  }, [authed, authError]);

  // Fallback polling when WS is down but Spotify is ok and connected
  useEffect(() => {
    if (!shouldPollHttpMusic) return;
    let mounted = true;
    const poll = async () => {
      try {
        const state = await getMusicState();
        if (mounted) setMusicState(state);
        // also nudge queue refreshers
        try {
          const ev = new CustomEvent('music.queue.updated', { detail: { source: 'http-poll' } });
          window.dispatchEvent(ev);
        } catch { /* noop */ }
      } catch { /* ignore */ }
    };
    const id = window.setInterval(poll, 5000);
    poll();
    return () => { mounted = false; window.clearInterval(id); };
  }, [shouldPollHttpMusic]);

  // WebSocket connection - only when authenticated
  useEffect(() => {
    if (!authed) {
      // Stop WebSocket connections when not authenticated
      try {
        wsHub.stop({ music: true, care: true });
      } catch (error) {
        console.error('Failed to stop WebSocket connections:', error);
      }
      return;
    }

    // Only start WebSocket connections when authenticated and auth state is stable
    const authOrchestrator = getAuthOrchestrator();
    const authState = authOrchestrator.getState();

    if (authState.is_authenticated && authState.session_ready) {
      try {
        wsHub.start({ music: true, care: true });
      } catch (error) {
        console.error('Failed to start WebSocket connections:', error);
      }
    }

    return () => {
      try {
        wsHub.stop({ music: true, care: true });
      } catch (error) {
        console.error('Failed to stop WebSocket connections:', error);
      }
    };
  }, [authed]);

  // Health polling now handled by <StatusBanner />

  // Persist messages after each update & auto‑scroll
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(
        historyKey,
        JSON.stringify(messages.filter(m => !m.loading).slice(-100)),
      );
    }
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Persist model selection
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(modelKey, model);
    }
  }, [model]);

  // Guard model selection when LLaMA is degraded; force auto and show inline hint
  useEffect(() => {
    if (!llamaDegraded) { setModelHint(null); return; }
    if (model.toLowerCase().startsWith('llama')) {
      setModel('auto');
      setModelHint('LLaMA is degraded—temporarily forcing auto.');
    } else {
      setModelHint('LLaMA is degraded—auto recommended.');
    }
  }, [llamaDegraded]);

  const handleSend = async (content: string) => {
    if (!content.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: content.trim(),
    };

    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      loading: true,
    };

    setMessages(prev => [...prev, userMessage, assistantMessage]);
    setLoading(true);

    try {
      const response = await sendPrompt(content.trim(), 'auto');

      setMessages(prev => prev.map(msg =>
        msg.id === assistantMessage.id
          ? { ...msg, content: response, loading: false }
          : msg
      ));

      // Save to localStorage
      const updatedMessages = [...messages, userMessage, { ...assistantMessage, content: response, loading: false }];
      localStorage.setItem(historyKey, JSON.stringify(updatedMessages));
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => prev.map(msg =>
        msg.id === assistantMessage.id
          ? { ...msg, content: 'Sorry, I encountered an error. Please try again.', loading: false }
          : msg
      ));
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => {
    setMessages([createInitialMessage()]);
    localStorage.removeItem(historyKey);
  };

  // Show loading state while auth is being determined (server renders skeleton)
  if (!mounted || authState.isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Checking authentication...</p>
        </div>
      </div>
    );
  }

  // Show auth error if there is one
  if (authState.error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-destructive mb-4">Authentication error: {authState.error}</p>
          <Button onClick={() => authOrchestrator.refreshAuth()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // Show login prompt if not authenticated
  if (!authed) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center max-w-md mx-auto p-6">
          <h1 className="text-2xl font-bold mb-4">Welcome to Gesahni</h1>
          <p className="text-muted-foreground mb-6">
            Please sign in to start chatting with your AI assistant.
          </p>
          <Link href="/login">
            <Button className="w-full">Login</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <RateLimitToast />
      <AuthMismatchToast />
      <StatusBanner />

      {/* Auth Finish Error */}
      {finishError && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-2 text-center">
          <p className="text-sm">Authentication failed: {finishError}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (typeof window !== 'undefined' && window.location) {
                window.location.reload();
              }
            }}
            className="mt-2"
          >
            Retry
          </Button>
        </div>
      )}

      {/* Backend offline/degraded banners handled by <StatusBanner /> */}

      {/* Main Content */}
      <div className="flex-1 flex flex-col lg:flex-row gap-6 p-6">
        {/* Chat Section */}
        <div className="flex-1 flex flex-col">
          <div className="flex-1 overflow-y-auto space-y-4 mb-4">
            {messages.length === 0 ? (
              <EmptyState />
            ) : (
              messages.map((message) => (
                <ChatBubble key={message.id} role={message.role} text={message.content} />
              ))
            )}
            {loading && <LoadingBubble />}
          </div>
          <InputBar
            onSend={handleSend}
            loading={loading}
            authed={authed}
          />
          {modelHint && (
            <div className="mt-2 text-xs text-amber-700 dark:text-amber-300" role="status" aria-live="polite">{modelHint}</div>
          )}
          <div className="flex justify-between items-center mt-4 text-sm text-muted-foreground">
            <span>Connected as {authState.user?.id || 'Unknown'}</span>
            <div className="flex items-center gap-4">
              <WebSocketStatus showDetails={true} />
              <Button variant="ghost" size="sm" onClick={clearHistory}>
                Clear History
              </Button>
            </div>
          </div>
        </div>

        {/* Music Section */}
        {authError && (
          <div className="w-full lg:w-80">
            <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-lg">
              <p className="text-sm font-medium mb-2">Music Access Required</p>
              <p className="text-xs mb-3">{authError}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setAuthError(null);
                  musicStateFetchAttempted.current = false;
                  // Trigger a fresh auth check
                  authOrchestrator.refreshAuth();
                }}
                className="w-full"
              >
                Retry
              </Button>
            </div>
          </div>
        )}

        {/* Right-rail: show static placeholders when WS down */}
        {(!authError) && (
          <div className="w-full lg:w-80 space-y-4">
            {musicUiReady ? (
              <>
                {musicState && <NowPlayingCard state={musicState} />}
                <DiscoveryCard />
                <MoodDial />
                <QueueCard />
                <DevicePicker />
              </>
            ) : (
              <>
                <div className="rounded-lg border p-4 text-sm text-muted-foreground" role="status" aria-live="polite">
                  <div>Music service unavailable. Showing static controls.</div>
                  <div className="mt-1 text-xs">{musicDegradedReason}</div>
                </div>
                {!hasDevice && spotifyConnected && (
                  <div className="rounded-lg border p-4 text-sm">
                    No device available — open Spotify on a device or select one below.
                    <div className="mt-2"><DevicePicker /></div>
                  </div>
                )}
                <div className="rounded-lg border p-4"><div className="h-4 bg-muted rounded w-1/2" /><div className="mt-2 h-3 bg-muted rounded w-2/3" /></div>
                <div className="rounded-lg border p-4"><div className="h-40 bg-muted rounded" /></div>
                <div className="rounded-lg border p-4"><div className="h-24 bg-muted rounded" /></div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Footer: WS indicators + model picker */}
      <div className="border-t px-6 py-2 flex items-center justify-between">
        <WsIndicator />
        <ModelSelector value={model} onChange={setModel} />
      </div>
    </div>
  );
}
