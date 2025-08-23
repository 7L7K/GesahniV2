"use client";

import Link from "next/link";

export default function TvHome() {
    return (
        <main className="min-h-screen bg-black text-white flex flex-col items-center justify-center gap-8">
            <h1 className="text-[72px] leading-tight font-bold">Granny Mode</h1>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-8 w-[90vw] max-w-6xl">
                {[
                    { label: "Weather", href: "/tv/weather" },
                    { label: "Calendar", href: "/tv/calendar" },
                    { label: "Music", href: "/tv/music" },
                    { label: "Photos", href: "/tv/photos" },
                    { label: "Live", href: "/tv/live" },
                    { label: "Contacts", href: "/tv/contacts" },
                ].map((t) => (
                    <Link key={t.href} href={t.href} className="bg-zinc-800 rounded-3xl p-12 text-[48px] text-center focus:outline-none focus:ring-8 focus:ring-blue-500">
                        {t.label}
                    </Link>
                ))}
            </div>
            <div className="opacity-80 text-2xl">Press and hold the Talk button to speak</div>
        </main>
    );
}
