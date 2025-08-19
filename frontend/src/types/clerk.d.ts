declare global {
    interface Window {
        Clerk?: {
            session?: {
                getToken(): Promise<string | null>;
            };
            addListener(callback: (event: { user: any; session: any }) => void): void;
            removeListener(callback: (event: { user: any; session: any }) => void): void;
        };
        __clerkToken?: string;
    }
}

export { };
