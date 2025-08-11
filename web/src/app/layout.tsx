import "../styles/globals.css";
import React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "../lib/queryClient";
import { SkipLink } from "../components/a11y/SkipLink";
import { Header } from "../components/layout/Header";

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <body>
                <SkipLink />
                <QueryClientProvider client={queryClient}>
                    <Header />
                    <main id="main" tabIndex={-1}>
                        {children}
                    </main>
                </QueryClientProvider>
            </body>
        </html>
    );
}


