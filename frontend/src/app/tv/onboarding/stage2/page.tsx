"use client";

export default function Stage2() {
    const tiles = [
        { key: "morning", label: "Morning check-in" },
        { key: "news", label: "Daily news" },
        { key: "music", label: "Music after lunch" },
        { key: "photos", label: "Evening photos" },
        { key: "reminders", label: "Gentle reminders" },
    ];
    return (
        <main className="min-h-screen bg-black text-white p-8 max-w-5xl mx-auto">
            <h1 className="text-4xl font-bold mb-8">Let’s make it yours</h1>
            <div className="grid grid-cols-2 gap-6">
                {tiles.map(t => (
                    <button key={t.key} className="bg-zinc-800 rounded-2xl p-10 text-2xl text-left">
                        {t.label}
                    </button>
                ))}
            </div>
            <div className="mt-10">
                <a href="/tv" className="bg-white text-black px-6 py-4 rounded-2xl text-2xl">Finish</a>
            </div>
        </main>
    );
}
