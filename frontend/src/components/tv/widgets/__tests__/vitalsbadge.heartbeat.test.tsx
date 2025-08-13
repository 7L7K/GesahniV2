import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { VitalsBadge } from '../../widgets/VitalsBadge';

jest.useFakeTimers();

describe('VitalsBadge heartbeat/live-stale indicator', () => {
  it('toggles to Reconnecting… when pings stop', () => {
    render(<VitalsBadge />);
    // Initially, no events; may show Offline or Reconnecting depending on navigator.onLine
    // Simulate a ping event to mark live
    window.dispatchEvent(new Event('music.state'));
    expect(screen.getByText(/Online|Reconnecting|Offline/)).toBeInTheDocument();
    // Advance time by >60s without events
    jest.advanceTimersByTime(61_000);
    // Force a re-render trigger by dispatching a benign event
    window.dispatchEvent(new Event('focus'));
    expect(screen.getByText(/Reconnecting/i)).toBeInTheDocument();
  });
});



