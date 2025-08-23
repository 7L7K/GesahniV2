import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import Page from '../page';

jest.mock('@/lib/api', () => ({
  apiFetch: jest.fn(async (_: string, __: any) => ({
    json: async () => ({ items: [{ time: '10:00', title: 'Doctor' }] })
  }))
}));

describe('TV Calendar page', () => {
  it('renders next items and matches snapshot', async () => {
    const { container } = render(<Page />);
    await waitFor(() => expect(screen.getByText(/Doctor/)).toBeInTheDocument());
    expect(container.firstChild).toMatchSnapshot();
  });
});
