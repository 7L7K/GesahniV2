// Simple toast utility for the frontend
export interface ToastOptions {
    message: string;
    type?: 'success' | 'error' | 'warning' | 'info';
    duration?: number;
}

export function showToast(options: ToastOptions) {
    const { message, type = 'info', duration = 5000 } = options;

    // Create toast event
    const event = new CustomEvent('show-toast', {
        detail: { message, type, duration }
    });

    if (typeof window !== 'undefined') {
        window.dispatchEvent(event);
    }
}

// Convenience methods
export const toast = {
    success: (message: string, duration?: number) => showToast({ message, type: 'success', duration }),
    error: (message: string, duration?: number) => showToast({ message, type: 'error', duration }),
    warning: (message: string, duration?: number) => showToast({ message, type: 'warning', duration }),
    info: (message: string, duration?: number) => showToast({ message, type: 'info', duration }),
};
