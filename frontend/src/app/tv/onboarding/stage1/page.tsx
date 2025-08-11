"use client";

import { useState } from "react";

export default function Stage1() {
    const [name, setName] = useState("");
    const [speechRate, setSpeechRate] = useState("slow");
    const [inputMode, setInputMode] = useState("ptt");
    const [fontSize, setFontSize] = useState("large");
    const [addressStyle, setAddressStyle] = useState("first_name");
    return (
        <main className="min-h-screen bg-black text-white p-8 max-w-4xl mx-auto space-y-6">
            <h1 className="text-4xl font-bold">Welcome</h1>
            <label className="block text-2xl">Your name
                <input className="block mt-2 text-black p-3 rounded" value={name} onChange={e => setName(e.target.value)} />
            </label>
            <label className="block text-2xl">Speech rate
                <select className="block mt-2 text-black p-3 rounded" value={speechRate} onChange={e => setSpeechRate(e.target.value)}>
                    <option value="slow">Slow</option>
                    <option value="normal">Normal</option>
                </select>
            </label>
            <label className="block text-2xl">Input mode
                <select className="block mt-2 text-black p-3 rounded" value={inputMode} onChange={e => setInputMode(e.target.value)}>
                    <option value="ptt">Push-to-Talk</option>
                    <option value="wake">Wake word</option>
                </select>
            </label>
            <label className="block text-2xl">Font size
                <select className="block mt-2 text-black p-3 rounded" value={fontSize} onChange={e => setFontSize(e.target.value)}>
                    <option value="large">Large</option>
                    <option value="xlarge">Extra Large</option>
                </select>
            </label>
            <label className="block text-2xl">Address me by
                <select className="block mt-2 text-black p-3 rounded" value={addressStyle} onChange={e => setAddressStyle(e.target.value)}>
                    <option value="first_name">First name</option>
                    <option value="nickname">Nickname</option>
                </select>
            </label>
            <div className="pt-4">
                <a href="/tv/onboarding/stage2" className="bg-white text-black px-6 py-4 rounded-2xl text-2xl">Next</a>
            </div>
        </main>
    );
}



