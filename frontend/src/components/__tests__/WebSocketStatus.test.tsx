import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WebSocketStatus } from '../WebSocketStatus';
import { wsHub } from '@/services/wsHub';

// Mock the wsHub
jest.mock('@/services/wsHub');
const mockWsHub = wsHub as jest.Mocked<typeof wsHub>;

describe('WebSocketStatus', () => {
    beforeEach(() => {
        jest.clearAllMocks();

        // Mock getConnectionStatus to return default values
        mockWsHub.getConnectionStatus.mockImplementation((_name) => ({
            isOpen: false,
            isConnecting: false,
            failureReason: null,
            lastFailureTime: 0,
        }));
    });

    it('renders connection status indicators', () => {
        render(<WebSocketStatus />);

        expect(screen.getByText('Music WS: Disconnected')).toBeInTheDocument();
        expect(screen.getByText('Care WS: Disconnected')).toBeInTheDocument();
    });

    it('shows connected status when WebSocket is open', () => {
        mockWsHub.getConnectionStatus.mockImplementation((_name) => ({
            isOpen: true,
            isConnecting: false,
            failureReason: null,
            lastFailureTime: 0,
        }));

        render(<WebSocketStatus />);

        expect(screen.getByText('Music WS: Connected')).toBeInTheDocument();
        expect(screen.getByText('Care WS: Connected')).toBeInTheDocument();
    });

    it('shows connecting status when WebSocket is connecting', () => {
        mockWsHub.getConnectionStatus.mockImplementation((_name) => ({
            isOpen: false,
            isConnecting: true,
            failureReason: null,
            lastFailureTime: 0,
        }));

        render(<WebSocketStatus />);

        expect(screen.getByText('Music WS: Connecting...')).toBeInTheDocument();
        expect(screen.getByText('Care WS: Connecting...')).toBeInTheDocument();
    });

    it('shows failed status when WebSocket has failed', () => {
        mockWsHub.getConnectionStatus.mockImplementation((_name) => ({
            isOpen: false,
            isConnecting: false,
            failureReason: 'Connection timeout',
            lastFailureTime: Date.now(),
        }));

        render(<WebSocketStatus />);

        expect(screen.getByText('Music WS: Failed')).toBeInTheDocument();
        expect(screen.getByText('Care WS: Failed')).toBeInTheDocument();
    });

    it('shows detailed status when showDetails is true', () => {
        const failureTime = Date.now();
        mockWsHub.getConnectionStatus.mockImplementation((name) => ({
            isOpen: false,
            isConnecting: false,
            failureReason: name === 'music' ? 'Connection timeout' : 'Network error',
            lastFailureTime: failureTime,
        }));

        render(<WebSocketStatus showDetails={true} />);

        expect(screen.getByText(/Music: Connection timeout/)).toBeInTheDocument();
        expect(screen.getByText(/Care: Network error/)).toBeInTheDocument();
    });

    it('does not show detailed status when showDetails is false', () => {
        mockWsHub.getConnectionStatus.mockImplementation((_name) => ({
            isOpen: false,
            isConnecting: false,
            failureReason: 'Connection timeout',
            lastFailureTime: Date.now(),
        }));

        render(<WebSocketStatus showDetails={false} />);

        expect(screen.queryByText(/Music: Connection timeout/)).not.toBeInTheDocument();
        expect(screen.queryByText(/Care: Network error/)).not.toBeInTheDocument();
    });

    it('shows connection failure hint when ws:connection_failed event is dispatched', async () => {
        render(<WebSocketStatus />);

        // Initially, no failure hint should be shown
        expect(screen.queryByText('WebSocket Connection Failed')).not.toBeInTheDocument();

        // Dispatch connection failed event
        const failureEvent = new CustomEvent('ws:connection_failed', {
            detail: {
                name: 'music',
                reason: 'Connection lost and max reconnection attempts reached',
                timestamp: Date.now(),
            },
        });

        window.dispatchEvent(failureEvent);

        // Should show failure hint
        await waitFor(() => {
            expect(screen.getByText('WebSocket Connection Failed')).toBeInTheDocument();
            expect(screen.getByText(/Music connection failed/)).toBeInTheDocument();
            expect(screen.getByText(/Connection will not automatically retry/)).toBeInTheDocument();
        });
    });

    it('auto-hides connection failure hint after 10 seconds', async () => {
        jest.useFakeTimers();

        render(<WebSocketStatus />);

        // Dispatch connection failed event
        const failureEvent = new CustomEvent('ws:connection_failed', {
            detail: {
                name: 'care',
                reason: 'Not authenticated',
                timestamp: Date.now(),
            },
        });

        window.dispatchEvent(failureEvent);

        // Should show failure hint
        await waitFor(() => {
            expect(screen.getByText('WebSocket Connection Failed')).toBeInTheDocument();
        });

        // Fast-forward 10 seconds
        jest.advanceTimersByTime(10000);

        // Should auto-hide
        await waitFor(() => {
            expect(screen.queryByText('WebSocket Connection Failed')).not.toBeInTheDocument();
        });

        jest.useRealTimers();
    });

    it('allows manual dismissal of connection failure hint', async () => {
        render(<WebSocketStatus />);

        // Dispatch connection failed event
        const failureEvent = new CustomEvent('ws:connection_failed', {
            detail: {
                name: 'music',
                reason: 'Connection timeout',
                timestamp: Date.now(),
            },
        });

        window.dispatchEvent(failureEvent);

        // Should show failure hint
        await waitFor(() => {
            expect(screen.getByText('WebSocket Connection Failed')).toBeInTheDocument();
        });

        // Click dismiss button
        const dismissButton = screen.getByText('×');
        fireEvent.click(dismissButton);

        // Should hide failure hint
        await waitFor(() => {
            expect(screen.queryByText('WebSocket Connection Failed')).not.toBeInTheDocument();
        });
    });

    it('updates status periodically', async () => {
        jest.useFakeTimers();

        render(<WebSocketStatus />);

        // Initial call
        expect(mockWsHub.getConnectionStatus).toHaveBeenCalledWith('music');
        expect(mockWsHub.getConnectionStatus).toHaveBeenCalledWith('care');

        // Fast-forward 1 second
        jest.advanceTimersByTime(1000);

        // Should call again
        await waitFor(() => {
            expect(mockWsHub.getConnectionStatus).toHaveBeenCalledTimes(4); // 2 initial + 2 after 1s
        });

        jest.useRealTimers();
    });

    it('cleans up event listeners on unmount', () => {
        const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');

        const { unmount } = render(<WebSocketStatus />);

        unmount();

        expect(removeEventListenerSpy).toHaveBeenCalledWith(
            'ws:connection_failed',
            expect.any(Function)
        );
    });

    it('applies custom className', () => {
        render(<WebSocketStatus className="custom-class" />);

        const container = screen.getByText('Music WS: Disconnected').closest('div')?.parentElement?.parentElement;
        expect(container).toHaveClass('custom-class');
    });

    it('formats failure time correctly', () => {
        const failureTime = new Date('2024-01-01T12:00:00').getTime();
        mockWsHub.getConnectionStatus.mockImplementation((_name) => ({
            isOpen: false,
            isConnecting: false,
            failureReason: 'Connection timeout',
            lastFailureTime: failureTime,
        }));

        render(<WebSocketStatus showDetails={true} />);

        // Should show formatted time (exact format depends on locale)
        expect(screen.getAllByText(/12:00:00/)).toHaveLength(2);
    });
});
