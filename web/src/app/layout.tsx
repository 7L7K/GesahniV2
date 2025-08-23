import '../styles/globals.css';
import React from 'react';
import { Providers } from './providers';

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <body>
                <Providers>
                    <main id="main" tabIndex={-1}>
                        {children}
                    </main>
                </Providers>
            </body>
        </html>
    );
}
