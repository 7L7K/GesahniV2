"use client";

export default function TvSettings() {
    return (
        <main className="min-h-screen bg-black text-white p-8">
            <h1 className="text-4xl font-bold mb-8">Granny Mode Settings</h1>
            <div className="space-y-6 text-2xl">
                <label className="flex items-center gap-4">
                    <input type="checkbox" defaultChecked className="h-8 w-8" /> Slow TTS
                </label>
                <label className="flex items-center gap-4">
                    <input type="checkbox" defaultChecked className="h-8 w-8" /> High contrast
                </label>
                <label className="flex items-center gap-4">
                    <input type="checkbox" defaultChecked className="h-8 w-8" /> Large text
                </label>
            </div>
        </main>
    );
}


