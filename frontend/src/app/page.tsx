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
import Link from 'next/link';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
}

// Clerk completely removed - using cookie authentication only

export default function Page() {
  const router = useRouter();
  const authState = useAuthState();
  const authOrchestrator = useAuthOrchestrator();
  const bootstrapManager = useBootstrapManager();
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [sessionReady, setSessionReady] = useState<boolean>(false);
  const [backendOffline, setBackendOffline] = useState<boolean>(false);

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

  // Backend status check with bootstrap coordination
  useEffect(() => {
    // DISABLED: Health polling should be controlled by orchestrator
    // Health check state tracking
    // const healthCheckState = {
    //   hasEverSucceeded: false,
    //   lastSuccessTs: 0,
    //   lastCheckTs: 0,
    //   consecutiveFailures: 0,
    //   nextCheckDelay: 5000, // Start with 5 seconds
    //   maxCheckDelay: 300000, // Max 5 minutes
    //   successThrottleDelay: 60000, // 1 minute after success
    // };

    // const checkBackend = async () => {
    //   // Check if health polling is allowed by bootstrap manager
    //   if (!bootstrapManager.startHealthPolling()) {
    //     console.info('Page: Health polling blocked by bootstrap manager');
    //     return;
    //   }

    //   const now = Date.now();

    //   // Check if we should skip this health check due to throttling
    //   if (healthCheckState.hasEverSucceeded) {
    //     const timeSinceSuccess = now - healthCheckState.lastSuccessTs;
    //     if (timeSinceSuccess < healthCheckState.successThrottleDelay) {
    //       console.debug('Skipping health check - throttled after success (%dms remaining)',
    //         healthCheckState.successThrottleDelay - timeSinceSuccess);
    //       return;
    //     }
    //   }

    //   // Check if we should skip due to exponential backoff
    //   const timeSinceLastCheck = now - healthCheckState.lastCheckTs;
    //   if (!healthCheckState.hasEverSucceeded && timeSinceLastCheck < healthCheckState.nextCheckDelay) {
    //     console.debug('Skipping health check - exponential backoff (%dms remaining)',
    //       healthCheckState.nextCheckDelay - timeSinceLastCheck);
    //     return;
    //   }

    //   healthCheckState.lastCheckTs = now;

    //   try {
    //     const response = await apiFetch('/v1/status', { method: 'GET', auth: false });
    //     const isOnline = response.ok;
    //     setBackendOffline(!isOnline);

    //     if (isOnline) {
    //       // Success - update state
    //       healthCheckState.hasEverSucceeded = true;
    //       healthCheckState.lastSuccessTs = now;
    //       healthCheckState.consecutiveFailures = 0;
    //       healthCheckState.nextCheckDelay = 5000; // Reset to initial delay
    //       console.debug('Backend health check successful');
    //     } else {
    //       // Failure
    //       healthCheckState.consecutiveFailures += 1;

    //       // Exponential backoff: double the delay, capped at max_delay
    //       if (!healthCheckState.hasEverSucceeded) {
    //         healthCheckState.nextCheckDelay = Math.min(
    //           healthCheckState.nextCheckDelay * 2,
    //           healthCheckState.maxCheckDelay
    //         );
    //         console.warn('Backend health check failed (attempt %d, next check in %dms)',
    //           healthCheckState.consecutiveFailures,
    //           healthCheckState.nextCheckDelay);
    //       } else {
    //         console.warn('Backend health check failed after previous success');
    //       }
    //     }
    //   } catch {
    //     setBackendOffline(true);
    //     healthCheckState.consecutiveFailures += 1;

    //     // Exponential backoff: double the delay, capped at max_delay
    //     if (!healthCheckState.hasEverSucceeded) {
    //       healthCheckState.nextCheckDelay = Math.min(
    //         healthCheckState.nextCheckDelay * 2,
    //         healthCheckState.maxCheckDelay
    //       );
    //       console.warn('Backend health check failed (attempt %d, next check in %dms)',
    //         healthCheckState.consecutiveFailures,
    //         healthCheckState.nextCheckDelay);
    //     } else {
    //       console.warn('Backend health check failed after previous success');
    //     }
    //   } finally {
    //     // Always stop health polling when done
    //     bootstrapManager.stopHealthPolling();
    //   }
    // };

    // checkBackend();

    // // Use a more intelligent interval that adapts based on health check state
    // const interval = setInterval(() => {
    //   const now = Date.now();
    //   let delay = 30000; // Default 30 seconds

    //   if (healthCheckState.hasEverSucceeded) {
    //     // After success: throttle to once per minute
    //     delay = healthCheckState.successThrottleDelay;
    //   } else {
    //     // Before success: use exponential backoff
    //     delay = healthCheckState.nextCheckDelay;
    //   }

    //   // Schedule next check
    //   setTimeout(checkBackend, delay);
    // }, 30000); // Check every 30 seconds initially, then adapt

    // return () => {
    //   clearInterval(interval);
    //   bootstrapManager.stopHealthPolling();
    // };
  }, [bootstrapManager]);

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

  // Show loading state while auth is being determined
  if (authState.isLoading) {
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

      {/* Backend Offline Notice */}
      {backendOffline && (
        <div className="bg-yellow-500/10 border border-yellow-500/20 text-yellow-700 dark:text-yellow-300 px-4 py-2 text-center">
          <p className="text-sm">Backend is offline. Some features may be unavailable.</p>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex flex-col lg:flex-row gap-6 p-6">
        {/* Chat Section */}
        <div className="flex-1 flex flex-col">
          <div className="flex-1 overflow-y-auto space-y-4 mb-4">
            {messages.length === 0 ? (
              <ChatBubble role="assistant" text={createInitialMessage().content} />
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
            model={model}
            onModelChange={setModel}
            authed={authed}
          />
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

        {musicState && !authError && (
          <div className="w-full lg:w-80 space-y-4">
            <NowPlayingCard state={musicState} />
            <DiscoveryCard />
            <MoodDial />
            <QueueCard />
            <DevicePicker />
          </div>
        )}
      </div>
    </div>
  );
}
