import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { CalendarCard, __test } from '../../widgets/CalendarCard';

jest.mock('@/lib/api', () => ({
  apiFetch: jest.fn(async () => ({
    json: async () => ({ items: [] })
  }))
}));

describe('CalendarCard', () => {
  it('renders graceful empty state', async () => {
    render(<CalendarCard />);
    const el = await screen.findByText(/No upcoming events/i);
    expect(el).toBeInTheDocument();
  });

  it('computes leave-by when within window and travel provided', () => {
    const now = new Date('2025-01-01T09:00:00Z');
    const start = new Date('2025-01-01T09:20:00Z');
    const s = __test.computeLeaveBy(now, { startIso: start.toISOString(), travelMinutes: 10, bufferMinutes: 5 });
    // now + travel (09:10) >= start - buffer (09:15) => leave-by = 09:05
    expect(s).toBeTruthy();
  });

  it('does not compute leave-by when no travel', () => {
    const s = __test.computeLeaveBy(new Date(), { time: '10:00', travelMinutes: null, bufferMinutes: 5 });
    expect(s).toBeNull();
  });
});


