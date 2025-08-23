"use client";

import Link from "next/link";

export function BigButtons() {
    const items = [
        { label: "Weather", href: "/tv/weather" },
        { label: "Calendar", href: "/tv/calendar" },
        { label: "Music", href: "/tv/music" },
        { label: "Photos", href: "/tv/photos" },
    ];
    return (
        <div className="grid grid-cols-2 gap-6 w-full">
            {items.map((t) => (
                <Link key={t.href} href={t.href} className="bg-zinc-800 rounded-2xl p-10 text-3xl text-center">
                    {t.label}
                </Link>
            ))}
        </div>
    );
}
