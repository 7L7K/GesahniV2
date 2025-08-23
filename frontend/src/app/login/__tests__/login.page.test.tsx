/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

const { apiFetch, setTokens } = jest.requireMock('@/lib/api');

describe('LoginPage', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('renders the form', () => {
    render(<LoginPage />);
    expect(screen.getByLabelText('Username')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getAllByText('Sign in').length).toBeGreaterThan(0);
  });

  it('validates username format', async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: '!!' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'abcdefgh' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/Invalid username/)).toBeInTheDocument();
  });

  it('requires password length >= 8', async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'validuser' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'short' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/Password is too weak/)).toBeInTheDocument();
  });

  it('handles backend invalid credentials nicely', async () => {
    (apiFetch as jest.Mock).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'invalid credentials' }), { status: 401, headers: { 'Content-Type': 'application/json' } }));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'john' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'abcdefgh' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Incorrect username or password.')).toBeInTheDocument();
  });

  it('logs user in and stores tokens', async () => {
    (apiFetch as jest.Mock)
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'a', refresh_token: 'b' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'john' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'abcdefgh' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(setTokens).toHaveBeenCalledWith('a', 'b'));
  });

  it('starts Google login flow', async () => {
    (apiFetch as jest.Mock).mockResolvedValueOnce(new Response(JSON.stringify({ auth_url: 'https://accounts.google.com/...'}), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const assignSpy = jest.fn();
    Object.defineProperty(window, 'location', {
      value: { href: '', assign: assignSpy },
      writable: true,
    } as any);
    render(<LoginPage />);
    fireEvent.click(screen.getByRole('button', { name: /Continue with Google/i }));
    await waitFor(() => expect(assignSpy).toHaveBeenCalled());
  });
});
