/**
 * Authentication event handling and dispatching
 */

import type { AuthState } from './types';

export interface AuthTokensSetEvent {
  userId: string | null;
  source: string;
  timestamp: number;
}

export interface AuthTokensClearedEvent {
  reason: string | null;
  timestamp: number;
}

export interface AuthStateChangedEvent {
  prevState: {
    is_authenticated: boolean;
    session_ready: boolean;
    user_id: string | null;
  };
  newState: {
    is_authenticated: boolean;
    session_ready: boolean;
    user_id: string | null;
  };
  timestamp: number;
}

export class AuthEventDispatcher {
  dispatchAuthStateEvents(prevState: AuthState, newState: AuthState): void {
    // Dispatch events for WebSocket hub and other components that listen for auth changes
    if (typeof window === 'undefined') return;

    try {
      // Dispatch tokens_set when authentication state changes to authenticated
      if (!prevState.is_authenticated && newState.is_authenticated && newState.session_ready) {
        console.info('AUTH Orchestrator: Dispatching auth:tokens_set event');
        window.dispatchEvent(new CustomEvent<AuthTokensSetEvent>('auth:tokens_set', {
          detail: {
            userId: newState.user_id,
            source: newState.source,
            timestamp: Date.now()
          }
        }));
      }

      // Dispatch tokens_cleared when authentication state changes to unauthenticated
      if (prevState.is_authenticated && !newState.is_authenticated) {
        console.info('AUTH Orchestrator: Dispatching auth:tokens_cleared event');
        window.dispatchEvent(new CustomEvent<AuthTokensClearedEvent>('auth:tokens_cleared', {
          detail: {
            reason: newState.error || 'logout',
            timestamp: Date.now()
          }
        }));
      }

      // Dispatch auth state change for general consumption
      window.dispatchEvent(new CustomEvent<AuthStateChangedEvent>('auth:state_changed', {
        detail: {
          prevState: {
            is_authenticated: prevState.is_authenticated,
            session_ready: prevState.session_ready,
            user_id: prevState.user_id
          },
          newState: {
            is_authenticated: newState.is_authenticated,
            session_ready: newState.session_ready,
            user_id: newState.user_id
          },
          timestamp: Date.now()
        }
      }));

    } catch (error) {
      console.warn('AUTH Orchestrator: Failed to dispatch auth state events', error);
    }
  }

  dispatchAuthEpochBumped(): void {
    if (typeof window === 'undefined') return;
    try {
      window.dispatchEvent(new Event('auth:epoch_bumped'));
    } catch (error) {
      console.warn('AUTH Orchestrator: Failed to dispatch auth epoch bumped event', error);
    }
  }

  dispatchAuthMismatch(message: string, timestamp: string): void {
    if (typeof window === 'undefined') return;
    try {
      const ev = new CustomEvent('auth-mismatch', {
        detail: {
          message,
          timestamp
        }
      });
      window.dispatchEvent(ev);
    } catch (error) {
      console.warn('AUTH Orchestrator: Failed to dispatch auth mismatch event', error);
    }
  }
}
