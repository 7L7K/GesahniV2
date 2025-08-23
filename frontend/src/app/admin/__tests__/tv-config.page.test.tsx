import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import Page from '../tv-config/page';

jest.mock('@/lib/api', () => ({
  getTvConfig: jest.fn(async () => ({ status: 'ok', config: { ambient_rotation: 30, rail: 'safe', quiet_hours: { start: '22:00', end: '06:00' }, default_vibe: 'Calm Night' } })),
  putTvConfig: jest.fn(async (_r: string, _t: string, cfg: any) => ({ status: 'ok', config: cfg })),
}));

describe('Admin TV Config editor', () => {
  it('blocks invalid config and allows valid save', async () => {
    render(<Page />);
    const ta = (await screen.findAllByRole('textbox')).pop()!;
    // invalid: rail
    fireEvent.change(ta, { target: { value: '{"ambient_rotation":30,"rail":"x","default_vibe":"Calm Night"}' } });
    expect(await screen.findByText(/rail must be/i)).toBeInTheDocument();
    // valid
    fireEvent.change(ta, { target: { value: '{"ambient_rotation":30,"rail":"safe","default_vibe":"Calm Night"}' } });
    expect(screen.queryByText(/rail must be/i)).toBeNull();
    const btn = screen.getByRole('button', { name: /Save & Apply/i });
    fireEvent.click(btn);
    await waitFor(() => expect(btn).toHaveTextContent(/Saving|Save/));
  });
});
