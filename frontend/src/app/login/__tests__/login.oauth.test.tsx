/** @jest-environment jsdom */
import React from 'react';
import { render, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import LoginPage from '../page';

const replaceMock = jest.fn();

// Dynamic mock to control search params
let params: Record<string, string | null> = {};
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: jest.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k in params ? params[k] : null) }),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    setTokens: jest.fn(),
    apiFetch: jest.fn(),
  };
});

const { setTokens } = jest.requireMock('@/lib/api');

describe('LoginPage OAuth capture', () => {
  beforeEach(() => {
    params = {};
    replaceMock.mockReset();
    (setTokens as jest.Mock).mockReset();
  });

  it('captures access_token from query and redirects', async () => {
    params = { access_token: 'a', refresh_token: 'b', next: '/chat' };
    render(<LoginPage />);
    await waitFor(() => expect(setTokens).toHaveBeenCalledWith('a', 'b'));
    expect(replaceMock).toHaveBeenCalledWith('/chat');
  });

  it('ignores when no access_token present', async () => {
    params = { next: '/chat' };
    render(<LoginPage />);
    await new Promise(r => setTimeout(r, 10));
    expect(setTokens).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('sanitizes next param to prevent open redirects', async () => {
    params = { access_token: 'a', refresh_token: 'b', next: 'https://evil.com' };
    render(<LoginPage />);
    await waitFor(() => expect(setTokens).toHaveBeenCalled());
    expect(replaceMock).toHaveBeenCalledWith('/');
  });
});
