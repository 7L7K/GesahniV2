import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "next-themes";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import Header from "@/components/Header";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";

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
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <QueryClientProvider client={queryClient}>
            <div className="min-h-screen grid grid-rows-[auto_1fr]">
              <Header />
              <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 bg-primary text-primary-foreground rounded px-3 py-2">Skip to content</a>
              <div id="main" className="bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-50 via-background to-background dark:from-zinc-900/20">
                {children}
              </div>
            </div>
            <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
          </QueryClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
