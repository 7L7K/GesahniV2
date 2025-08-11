"use client";

import Link from "next/link";

export default function TvHome() {
    return (
        <main className="min-h-screen bg-black text-white flex flex-col items-center justify-center gap-8">
            <h1 className="text-5xl font-bold">Granny Mode</h1>
            <div className="grid grid-cols-2 gap-6 w-[80vw] max-w-4xl">
                {[
                    { label: "Weather", href: "/tv/weather" },
                    { label: "Calendar", href: "/tv/calendar" },
                    { label: "Music", href: "/tv/music" },
                    { label: "Photos", href: "/tv/photos" },
                ].map((t) => (
                    <Link key={t.href} href={t.href} className="bg-zinc-800 rounded-2xl p-10 text-3xl text-center">
                        {t.label}
                    </Link>
                ))}
            </div>
            <div className="opacity-75">Press and hold the Talk button to speak</div>
        </main>
    );
}


