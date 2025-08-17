import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Docs | Gesahni",
    description: "User Guide for GesahniV2",
    metadataBase: new URL(
        (process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL || "http://127.0.0.1:3000") as string,
    ),
};

const nav = [
    { href: "/docs", label: "Overview" },
    { href: "/docs/getting-started", label: "Getting Started" },
    { href: "/docs/chat", label: "Chat" },
    { href: "/docs/home-assistant", label: "Home Assistant" },
    { href: "/docs/voice", label: "Voice & Sessions" },
    { href: "/docs/skills", label: "Skills" },
    { href: "/docs/model-routing", label: "Model Routing" },
    { href: "/docs/memory", label: "Memory & RAG" },
    { href: "/docs/proactive", label: "Proactive" },
    { href: "/docs/security", label: "Security" },
    { href: "/docs/admin", label: "Admin" },
    { href: "/docs/troubleshooting", label: "Troubleshooting" },
    { href: "/docs/faq", label: "FAQ" },
];

export default function DocsLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="mx-auto max-w-5xl px-4 py-6 grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6">
            <aside className="md:sticky md:top-16 h-max">
                <nav className="space-y-1 text-sm">
                    {nav.map((item) => (
                        <Link
                            key={item.href}
                            href={item.href}
                            className="block rounded px-2 py-1 text-muted-foreground hover:text-foreground hover:bg-accent"
                        >
                            {item.label}
                        </Link>
                    ))}
                </nav>
            </aside>
            <main className="prose prose-zinc dark:prose-invert max-w-none">
                {children}
            </main>
        </div>
    );
}


