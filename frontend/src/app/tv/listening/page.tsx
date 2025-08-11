"use client";

export default function Listening() {
    return (
        <main className="min-h-screen bg-black text-white flex flex-col items-center justify-center">
            <div className="text-4xl mb-6">Listening…</div>
            <div className="text-2xl opacity-75">You said: <span className="font-mono">(waiting)</span></div>
        </main>
    );
}


