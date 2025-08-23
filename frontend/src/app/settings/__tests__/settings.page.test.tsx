/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import SettingsPage from '../page';

// Router and data fetching mocks
const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: (opts: any) => opts.queryFn && { data: null, isLoading: false, error: null },
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    useProfile: jest.fn(),
    updateProfile: jest.fn(),
  };
});

const { useProfile, updateProfile } = jest.requireMock('@/lib/api');

describe('SettingsPage', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('shows loading spinner when loading', () => {
    (useProfile as jest.Mock).mockReturnValue({ data: null, isLoading: true, error: null });
    render(<SettingsPage />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders form with profile data', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: { name: 'Alice', email: 'a@b.com', language: 'en', timezone: 'America/New_York' }, isLoading: false, error: null });
    render(<SettingsPage />);
    expect(await screen.findByDisplayValue('Alice')).toBeInTheDocument();
    expect(screen.getByDisplayValue('a@b.com')).toBeInTheDocument();
    // Timezone default present
    expect((screen.getByLabelText('Timezone') as HTMLSelectElement).value).toBe('America/New_York');
  });

  it('redirects to /login on 401/403 error', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: null, isLoading: false, error: new Error('HTTP 401') });
    render(<SettingsPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'));
  });

  it('does not redirect on other errors, shows failed state', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: null, isLoading: false, error: new Error('HTTP 500') });
    render(<SettingsPage />);
    expect(await screen.findByText('Failed to load profile')).toBeInTheDocument();
  });

  it('updates fields and saves successfully', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: { name: 'Alice', email: 'a@b.com' }, isLoading: false, error: null });
    ;(updateProfile as jest.Mock).mockResolvedValueOnce(undefined);
    render(<SettingsPage />);
    fireEvent.change(await screen.findByLabelText('Full Name'), { target: { value: 'Alice B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(screen.getByText('Profile updated successfully.')).toBeInTheDocument());
  });

  it('shows error when save fails', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: { name: 'Bob' }, isLoading: false, error: null });
    ;(updateProfile as jest.Mock).mockRejectedValueOnce(new Error('profile_update_failed'));
    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(screen.getByText(/profile_update_failed/)).toBeInTheDocument());
  });
});
