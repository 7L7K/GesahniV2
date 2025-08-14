import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "next-themes";
import { ClerkProvider } from "@clerk/nextjs";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import Header from "@/components/Header";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import WsBootstrap from "@/components/WsBootstrap";

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
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {publishableKey ? (
          <ClerkProvider
            publishableKey={publishableKey}
            appearance={{ elements: { userButtonAvatarBox: 'h-6 w-6' } }}
          >
            <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
              <QueryClientProvider client={queryClient}>
                <div className="min-h-screen grid grid-rows-[auto_1fr]">
                  <AuthBootstrap />
                  <WsBootstrap />
                  <Header />
                  <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-primary text-primary-foreground rounded px-3 py-2">Skip to content</a>
                  <div id="main" className="bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-50 via-background to-background dark:from-zinc-900/20">
                    {children}
                  </div>
                </div>
                <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
              </QueryClientProvider>
            </ThemeProvider>
          </ClerkProvider>
        ) : (
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
            <QueryClientProvider client={queryClient}>
              <div className="min-h-screen grid grid-rows-[auto_1fr]">
                <AuthBootstrap />
                <WsBootstrap />
                <Header />
                <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-primary text-primary-foreground rounded px-3 py-2">Skip to content</a>
                <div id="main" className="bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-50 via-background to-background dark:from-zinc-900/20">
                  {children}
                </div>
              </div>
              <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
            </QueryClientProvider>
          </ThemeProvider>
        )}
      </body>
    </html>
  );
}

function AuthBootstrap() {
  if (typeof window !== 'undefined') {
    import("@/lib/api").then(({ apiFetch }) => {
      apiFetch("/v1/whoami", { method: "GET", auth: true })
        .then(async (res) => {
          try {
            const body = await res.json().catch(() => null as any)
            const ok = Boolean(body && (body.is_authenticated || (body.user_id && body.user_id !== 'anon')))
            console.info('[breadcrumb] whoami.authenticated', { ok, user_id: body?.user_id, session_ready: body?.session_ready })
          } catch { /* noop */ }
        }).catch(() => { /* ignore */ });
      // Lightweight periodic refresh to keep access fresh before expiry
      try {
        const intervalMs = Math.max(60_000, Number(process.env.NEXT_PUBLIC_REFRESH_POLL_MS || 10 * 60_000));
        const id = setInterval(async () => {
          try {
            const r = await apiFetch('/v1/auth/refresh', { method: 'POST' })
            console.info('[breadcrumb] finish.completed', { ok: r?.ok, status: r?.status })
          } catch (e) {
            console.info('[breadcrumb] finish.completed', { ok: false, error: (e as any)?.message })
          }
        }, intervalMs);
        window.addEventListener('beforeunload', () => clearInterval(id));
      } catch { /* noop */ }
    });
  }
  return null;
}
