import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import InputBar from '../InputBar';

describe('InputBar', () => {
    beforeEach(() => localStorage.clear());

    test('calls onSend on Enter without shift', async () => {
        const onSend = jest.fn();
        render(<InputBar onSend={onSend} loading={false} model="auto" onModelChange={() => { }} authed={true} />);
        const textarea = screen.getByPlaceholderText('Type a message…');
        fireEvent.change(textarea, { target: { value: 'hi' } });
        await act(async () => { fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' }); });
        expect(onSend).toHaveBeenCalledWith('hi');
    });

    test('disabled while loading', () => {
        render(<InputBar onSend={jest.fn()} loading={true} model="auto" onModelChange={() => { }} authed={true} />);
        const textarea = screen.getByPlaceholderText('Type a message…');
        expect(textarea).toBeDisabled();
    });

    test('disabled when unauthenticated via auth event', async () => {
        const { unmount } = render(<InputBar onSend={jest.fn()} loading={false} model="auto" onModelChange={() => { }} authed={false} />);
        const textarea = screen.getByPlaceholderText('Type a message…') as HTMLTextAreaElement;
        expect(textarea.disabled).toBe(true);
        unmount();
        render(<InputBar onSend={jest.fn()} loading={false} model="auto" onModelChange={() => { }} authed={true} />);
        const enabledTextarea = screen.getAllByPlaceholderText('Type a message…')[0] as HTMLTextAreaElement;
        expect(enabledTextarea.disabled).toBe(false);
    });
});
