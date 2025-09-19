// Check fetch availability and provide helpful debugging
if (typeof window !== 'undefined' && typeof fetch === 'undefined') {
  console.warn('⚠️  WARNING: Global fetch is not available in browser environment!');
  console.warn('⚠️  This may cause "Cannot access uninitialized variable" errors');
  console.warn('⚠️  Browser compatibility issue detected - continuing with fallback handling');

  // Don't show error page immediately - let the app handle it gracefully
  // The fetch.ts module will handle this case with proper error handling
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "next-themes";
// Clerk intentionally not used in cookie-only frontend; keep layout simple
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import Header from "@/components/Header";
// Status banners are now handled within the chat layout (authenticated)
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { getCSPPolicy, generateNonce } from "@/lib/csp";
import WsBootstrap from "@/components/WsBootstrap";
import AuthProvider from "@/components/AuthProvider";
import ClientOnly from "@/components/ClientOnly";
import { ConfigValidator } from "@/components/ConfigValidator";
import AuthHud from "@/components/AuthHUD";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import NavigationLogger from "@/components/NavigationLogger";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Gesahni",
  description: "Gesahni web interface for your AI assistant",
  // Ensure social images resolve to absolute URLs in OG/Twitter tags
  metadataBase: new URL(
    (process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL || "http://localhost:3000") as string,
  ),
  openGraph: {
    title: "Gesahni",
    description: "Gesahni web interface for your AI assistant",
    siteName: "Gesahni",
    images: [{ url: "/apple-touch-icon.png" }],
  },
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  other: {
    "Content-Security-Policy": getCSPPolicy(),
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <QueryClientProvider client={queryClient}>
            <AuthProvider>
              <div className="min-h-screen grid grid-rows-[auto_1fr]">
                <NavigationLogger />
                <WsBootstrap />
                <ClientOnly>
                  <Header />
                </ClientOnly>
                {/* Status banners moved to chat layout */}
                <ConfigValidator />
                <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-primary text-primary-foreground rounded px-3 py-2">Skip to content</a>
                <div id="main" className="bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-50 via-background to-background dark:from-zinc-900/20">
                  <ErrorBoundary>
                    {children}
                  </ErrorBoundary>
                </div>
                {process.env.NODE_ENV !== 'production' ? <AuthHud /> : null}
              </div>
            </AuthProvider>
            <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
          </QueryClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
