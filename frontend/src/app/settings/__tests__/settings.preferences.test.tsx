/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import SettingsPage from '../page';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    useProfile: jest.fn(),
    updateProfile: jest.fn(),
  };
});

const { useProfile } = jest.requireMock('@/lib/api');

describe('SettingsPage AI preferences', () => {
  it('defaults preferred_model to auto and allows change', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: { preferred_model: undefined }, isLoading: false, error: null });
    render(<SettingsPage />);
    const auto = await screen.findByRole('radio', { name: 'Auto (Recommended)' });
    const llama = screen.getByRole('radio', { name: 'LLaMA 3 (Local)' });
    expect((auto as HTMLInputElement).checked).toBe(true);
    fireEvent.click(llama);
    expect((llama as HTMLInputElement).checked).toBe(true);
  });

  it('toggles integrations switches', async () => {
    (useProfile as jest.Mock).mockReturnValue({ data: { gmail_integration: false, calendar_integration: true }, isLoading: false, error: null });
    render(<SettingsPage />);
    const checkboxes = screen.getAllByRole('checkbox');
    expect((checkboxes[0] as HTMLInputElement).checked).toBe(false);
    expect((checkboxes[1] as HTMLInputElement).checked).toBe(true);
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    expect((checkboxes[0] as HTMLInputElement).checked).toBe(true);
    expect((checkboxes[1] as HTMLInputElement).checked).toBe(false);
  });
});
