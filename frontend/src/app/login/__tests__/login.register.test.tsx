/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import LoginPage from '../page';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k === 'next' ? '/settings' : null) }),
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

describe('Login register flow', () => {
  beforeEach(() => jest.resetAllMocks());

  it('can switch to register mode and then login', async () => {
    (apiFetch as jest.Mock)
      // register response
      .mockResolvedValueOnce(new Response("{}", { status: 200, headers: { 'Content-Type': 'application/json' } }))
      // login after register
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'x', refresh_token: 'y' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    render(<LoginPage />);
    fireEvent.click(screen.getByText('Need an account? Register'));
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'newuser' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'abcdefgh' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(setTokens).toHaveBeenCalled());
  });
});


