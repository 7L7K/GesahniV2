import { useEffect, useState } from 'react';

interface Toast {
    id: string;
    message: string;
    type: 'success' | 'error' | 'warning' | 'info';
    duration: number;
}

export function ToastManager() {
    const [toasts, setToasts] = useState<Toast[]>([]);

    useEffect(() => {
        function onShowToast(e: Event) {
            const detail = (e as CustomEvent).detail;
            const toast: Toast = {
                id: Date.now().toString(),
                message: detail.message,
                type: detail.type || 'info',
                duration: detail.duration || 5000,
            };

            setToasts(prev => [...prev, toast]);

            // Auto-remove after duration
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== toast.id));
            }, toast.duration);
        }

        window.addEventListener('show-toast', onShowToast);
        return () => window.removeEventListener('show-toast', onShowToast);
    }, []);

    const removeToast = (id: string) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    };

    const getToastStyles = (type: string) => {
        switch (type) {
            case 'success':
                return 'bg-green-500 text-white';
            case 'error':
                return 'bg-red-500 text-white';
            case 'warning':
                return 'bg-yellow-500 text-black';
            case 'info':
            default:
                return 'bg-blue-500 text-white';
        }
    };

    if (toasts.length === 0) return null;

    return (
        <div className="fixed top-4 right-4 z-50 space-y-2">
            {toasts.map(toast => (
                <div
                    key={toast.id}
                    className={`max-w-sm w-full p-4 rounded-lg shadow-lg ${getToastStyles(toast.type)}`}
                >
                    <div className="flex items-center justify-between">
                        <span>{toast.message}</span>
                        <button
                            onClick={() => removeToast(toast.id)}
                            className="ml-4 text-current opacity-70 hover:opacity-100"
                        >
                            ×
                        </button>
                    </div>
                </div>
            ))}
        </div>
    );
}
