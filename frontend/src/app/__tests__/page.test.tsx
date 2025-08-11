import React from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import Page from '../page';

// Mock next/navigation useRouter
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn() }) }));

// Mock api helpers
jest.mock('@/lib/api', () => ({
    getToken: jest.fn(() => localStorage.getItem('auth:access_token')),
    sendPrompt: jest.fn(async (_t: string, _m: string, onToken?: (s: string) => void) => {
        onToken?.('hello '); onToken?.('world');
        return 'hello world';
    }),
    getOnboardingStatus: jest.fn(async () => ({ completed: true, steps: [], current_step: 0 })),
}));

// Polyfill/mocks missing browser APIs in JSDOM
Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
    value: jest.fn(),
    writable: true,
});

function seedStorage(k: string, v: unknown) { localStorage.setItem(k, JSON.stringify(v)); }
function getByTextContent(text: string) {
    return screen.getByText((content, node) => node?.textContent === text);
}

describe('Home Chat Page', () => {
    beforeEach(() => {
        localStorage.clear();
        (global as any).IntersectionObserver = class { observe() { } unobserve() { } disconnect() { } } as any;
    });

    test('seeds initial assistant message when no history', () => {
        render(<Page />);
        expect(screen.getByText(/Hey King/)).toBeInTheDocument();
    });

    test('hydrates from localStorage and trims to last 100', () => {
        const msgs = Array.from({ length: 120 }).map((_, i) => ({ id: `m${i}`, role: i % 2 ? 'assistant' : 'user', content: `c${i}` }));
        // seed for guest scope since no token in tests
        seedStorage('chat-history:guest', msgs);
        render(<Page />);
        expect(screen.queryByText('c0')).not.toBeInTheDocument();
        expect(screen.getByText('c119')).toBeInTheDocument();
    });

    test('persists messages to localStorage on update', async () => {
        render(<Page />);
        const textarea = screen.getByPlaceholderText('Type a message…');
        await act(async () => {
            fireEvent.change(textarea, { target: { value: 'hi' } });
            fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' });
        });
        const key = Object.keys(localStorage).find(k => k.includes('chat-history')) || 'chat-history:guest';
        const stored = JSON.parse(localStorage.getItem(key) || '[]');
        expect(stored.some((m: any) => m.content?.includes('hello world'))).toBe(true);
    });

    test('disables input and shows sign-in message when unauthenticated', async () => {
        render(<Page />);
        // ensure no token
        localStorage.removeItem('auth:access_token');
        // send a message
        const textarea = screen.getByPlaceholderText('Type a message…');
        await act(async () => {
            fireEvent.change(textarea, { target: { value: 'x' } });
            fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' });
        });
        expect(screen.getByText(/Please sign in to chat/)).toBeInTheDocument();
    });

    test('streams tokens into placeholder then sets final content', async () => {
        localStorage.setItem('auth:access_token', 't');
        render(<Page />);
        const textarea = screen.getByPlaceholderText('Type a message…');
        await act(async () => {
            fireEvent.change(textarea, { target: { value: 'hello' } });
            fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' });
        });
        // streamed content should appear
        await screen.findByText(/hello world/);
    });

    test('clear history resets to initial message', async () => {
        render(<Page />);
        const btn = screen.getByText('Clear history');
        await act(async () => { fireEvent.click(btn); });
        expect(screen.getByText(/Hey King/)).toBeInTheDocument();
    });

    test('onboarding redirect when not completed', async () => {
        const mod = await import('@/lib/api');
        (mod as any).getOnboardingStatus.mockResolvedValueOnce({ completed: false });
        const push = jest.fn();
        (jest.requireMock('next/navigation') as any).useRouter = () => ({ push, replace: jest.fn() });
        localStorage.setItem('auth:access_token', 't');
        render(<Page />);
        await waitFor(() => expect(push).toHaveBeenCalledWith('/onboarding'));
    });

    test('auth token events update UI', async () => {
        render(<Page />);
        const textarea = screen.getByPlaceholderText('Type a message…') as HTMLTextAreaElement;
        // unauthenticated: disabled
        expect(textarea.disabled).toBe(true);
        // simulate login
        localStorage.setItem('auth:access_token', 't');
        act(() => { window.dispatchEvent(new Event('auth:tokens_set')); });
        await waitFor(() => expect((screen.getByPlaceholderText('Type a message…') as HTMLTextAreaElement).disabled).toBe(false));
    });
});


