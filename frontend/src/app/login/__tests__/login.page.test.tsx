/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import LoginPage from '../page';

// Mocks
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k === 'next' ? '/chat' : null) }),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    apiFetch: jest.fn(),
    setTokens: jest.fn(),
  };
});

jest.mock('@/services/authOrchestrator', () => ({
  getAuthOrchestrator: () => ({
    getState: () => ({
      is_authenticated: false,
      session_ready: false,
      user_id: null,
      user: null,
      source: 'missing',
      version: 1,
      lastChecked: 0,
      isLoading: false,
      error: null,
      whoamiOk: false,
    }),
    refreshAuth: jest.fn().mockResolvedValue(void 0),
    subscribe: jest.fn(() => () => { }),
  }),
}));

const { apiFetch, setTokens } = jest.requireMock('@/lib/api');

describe('LoginPage', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('renders the form after auth check', async () => {
    render(<LoginPage />);
    // Wait for authentication check to complete and form to appear
    await waitFor(() => {
      expect(screen.getByLabelText('Username')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign in/i })).toBeInTheDocument();
  });

  it('shows loading during auth check', () => {
    render(<LoginPage />);
    // Initially shows loading state
    expect(screen.getByText('Checking authentication...')).toBeInTheDocument();
  });
});
